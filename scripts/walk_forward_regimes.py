"""Run walk-forward validation over persisted regime decisions."""

from __future__ import annotations

import argparse
import json
from datetime import date
from typing import Any

from nse_quant.core.settings import get_settings
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.regime_policy import select_regime_policy
from nse_quant.research.regime_risk_policy import (
    build_regime_risk_limits,
)
from nse_quant.research.trade_outcomes import load_trade_outcomes, summarize_outcomes
from nse_quant.research.walk_forward import (
    build_folds,
    evaluate_fold,
    summarize_fold_results,
)


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run walk-forward regime validation")

    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)

    return parser.parse_args()


def load_decisions_factory(store: DuckDBStore, symbol: str):
    def load_decisions(
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        rows = store.conn.execute(
            """
            SELECT
                d.ts,
                d.decision_type,
                d.payload,
                r.regime
            FROM decisions d
            LEFT JOIN market_regimes r
              ON r.symbol = d.underlying
             AND r.ts = (
                 SELECT MAX(regime.ts)
                 FROM market_regimes regime
                 WHERE regime.symbol = d.underlying
                   AND regime.ts <= d.ts
             )
            WHERE d.underlying = ?
              AND CAST(d.ts AS DATE) >= ?
              AND CAST(d.ts AS DATE) <= ?
              AND d.decision_type IN (
                  'signal',
                  'risk_rejected',
                  'dry_run',
                  'paper_filled'
              )
            ORDER BY d.ts
            """,
            [symbol, start_date, end_date],
        ).fetchall()

        decisions: list[dict[str, Any]] = []

        for ts, decision_type, payload_json, regime in rows:
            payload = json.loads(payload_json) if payload_json else {}
            proposal = payload.get("proposal") or {}

            decisions.append(
                {
                    "ts": ts,
                    "decision_type": decision_type,
                    "regime": regime or "UNKNOWN",
                    "proposal_id": proposal.get("proposal_id"),
                    "strategy": proposal.get("strategy"),
                }
            )

        return decisions

    return load_decisions


def evaluate_parameters(
    decisions: list[dict[str, Any]],
    parameters: dict[str, Any],
) -> dict[str, Any]:
    trades = 0
    wins = 0
    pnl = 0.0

    for decision in decisions:
        if decision["decision_type"] not in {
            "dry_run",
            "paper_filled",
        }:
            continue

        if not decision.get("proposal_id"):
            continue

        trades += 1

        # PnL is joined later by the reporting layer; this placeholder
        # intentionally avoids pretending to evaluate unrealized trades.
        pnl += 0.0

    return {
        "trades": trades,
        "wins": wins,
        "pnl": pnl,
    }


def evaluate_parameters_factory(store, symbol: str):
    def evaluate_parameters(
        decisions: list[dict[str, Any]],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        if not decisions:
            return {
                "trades": 0,
                "wins": 0,
                "pnl": 0.0,
            }

        start_date = decisions[0]["ts"].date()
        end_date = decisions[-1]["ts"].date()

        outcomes = load_trade_outcomes(
            store.conn,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

        metrics = summarize_outcomes(outcomes)
        metrics["regimes"] = sorted({outcome.regime for outcome in outcomes})

        return metrics

    return evaluate_parameters


def load_outcomes_factory(store: DuckDBStore, symbol: str):
    def load_outcomes(
        start_date: date,
        end_date: date,
    ) -> list[Any]:
        return load_trade_outcomes(
            store.conn,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

    return load_outcomes


def main() -> int:
    args = parse_args()
    settings = get_settings()
    store = DuckDBStore()
    evaluate_parameters = evaluate_parameters_factory(
        store,
        args.symbol,
    )
    load_outcomes = load_outcomes_factory(store, args.symbol)

    try:
        folds = build_folds(
            start_date=parse_date(args.start),
            end_date=parse_date(args.end),
            train_days=settings.walk_forward.train_days,
            test_days=settings.walk_forward.test_days,
            step_days=settings.walk_forward.step_days,
        )

        load_decisions = load_decisions_factory(
            store,
            args.symbol,
        )

        results = []

        for fold in folds:
            result = evaluate_fold(
                fold=fold,
                load_decisions=load_decisions,
                load_outcomes=load_outcomes,
                select_policy=select_regime_policy,
                evaluate_parameters=evaluate_parameters,
                min_train_trades=(settings.walk_forward.min_train_trades),
                min_test_trades=(settings.walk_forward.min_test_trades),
            )

            results.append(result)

            print(
                f"fold={result.fold.fold_id} "
                f"train={result.fold.train_start}..{result.fold.train_end} "
                f"test={result.fold.test_start}..{result.fold.test_end} "
                f"train_trades={result.train_metrics.get('trades', 0)} "
                f"test_trades={result.test_metrics.get('trades', 0)}"
            )

            training_policy = select_regime_policy(
                load_outcomes(
                    result.fold.train_start,
                    result.fold.train_end,
                )
            )

            risk_limits_by_regime = {
                regime: build_regime_risk_limits(
                    regime=regime,
                    policy=training_policy,
                    base_limits=settings.risk,
                ).__dict__
                for regime in training_policy.allowed_regimes
            }

            store.save_regime_policy(
                policy_id=(
                    f"{args.symbol}:"
                    f"{result.fold.test_start.isoformat()}:"
                    f"{result.fold.test_end.isoformat()}"
                ),
                symbol=args.symbol,
                train_start=result.fold.train_start,
                train_end=result.fold.train_end,
                test_start=result.fold.test_start,
                test_end=result.fold.test_end,
                policy=training_policy,
                risk_limits=risk_limits_by_regime,
            )

        summary = summarize_fold_results(results)

        print("\nWalk-forward summary")
        print(json.dumps(summary, indent=2, default=str))
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
