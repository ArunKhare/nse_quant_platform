"""Report decision outcomes by point-in-time market regime."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict

from nse_quant.persistence.duckdb_store import DuckDBStore

COVERAGE_TIERS = [
    (10, "INSUFFICIENT"),
    (30, "INITIAL_EVIDENCE"),
    (100, "USABLE"),
    (300, "STRONG"),
]


def coverage_tier(trade_count: int) -> str:
    for threshold, tier in COVERAGE_TIERS:
        if trade_count < threshold:
            return tier
    return "ROBUST"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report performance by market regime"
    )
    parser.add_argument("--symbol", default="NIFTY")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = DuckDBStore(read_only=True)

    try:
        decisions = store.conn.execute(
            """
            SELECT
                d.ts,
                d.decision_type,
                d.payload
            FROM decisions d
            WHERE d.underlying = ?
              AND d.decision_type IN (
                  'signal',
                  'risk_rejected',
                  'dry_run',
                  'paper_filled'
              )
            ORDER BY d.ts
            """,
            [args.symbol],
        ).fetchall()

        regimes = store.conn.execute(
            """
            SELECT ts, regime
            FROM market_regimes
            WHERE symbol = ?
            ORDER BY ts
            """,
            [args.symbol],
        ).fetchall()

        if not regimes:
            print(f"No regimes found for {args.symbol}")
            return 0

        regime_times = [row[0] for row in regimes]
        regime_labels = [row[1] for row in regimes]

        stats: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {
                "decisions": 0,
                "proposals": 0,
                "risk_rejections": 0,
                "trades": 0,
                "wins": 0,
                "pnl": 0.0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
            }
        )

        for decision_ts, decision_type, payload_json in decisions:
            regime = "UNKNOWN"

            for regime_ts, label in zip(
                regime_times,
                regime_labels,
            ):
                if regime_ts <= decision_ts:
                    regime = label
                else:
                    break

            bucket = stats[regime]
            bucket["decisions"] += 1

            if decision_type == "signal":
                bucket["proposals"] += 1
            elif decision_type == "risk_rejected":
                bucket["risk_rejections"] += 1

            if decision_type not in {"dry_run", "paper_filled"}:
                continue

            payload = json.loads(payload_json) if payload_json else {}
            proposal = payload.get("proposal") or {}
            proposal_id = proposal.get("proposal_id")

            if not proposal_id:
                continue

            bucket["trades"] += 1

            review = store.conn.execute(
                """
                SELECT realized_pnl
                FROM post_trade_reviews
                WHERE strategy_position_id LIKE ?
                ORDER BY closed_at DESC
                LIMIT 1
                """,
                [f"{proposal_id}%"],
            ).fetchone()

            if review is None:
                continue

            pnl = float(review[0])
            bucket["pnl"] += pnl

            if pnl > 0:
                bucket["wins"] += 1
                bucket["gross_profit"] += pnl
            else:
                bucket["gross_loss"] += abs(pnl)

        required_regimes = {
            "RANGE|LOW",
            "RANGE|HIGH",
            "BULL|NORMAL",
            "BEAR|HIGH",
        }

        print(f"Regime coverage for {args.symbol}")
        print(
            "regime,decisions,proposals,risk_rejections,trades,"
            "win_rate,avg_pnl,profit_factor,proposal_rate,"
            "risk_rejection_rate,coverage"
        )

        for regime in sorted(stats):
            bucket = stats[regime]
            trades = int(bucket["trades"])
            proposals = int(bucket["proposals"])
            rejections = int(bucket["risk_rejections"])
            decisions = int(bucket["decisions"])

            win_rate = (
                bucket["wins"] / trades if trades else 0.0
            )
            avg_pnl = bucket["pnl"] / trades if trades else 0.0
            profit_factor = (
                bucket["gross_profit"] / bucket["gross_loss"]
                if bucket["gross_loss"]
                else float("inf")
                if bucket["gross_profit"]
                else 0.0
            )
            proposal_rate = (
                proposals / decisions if decisions else 0.0
            )
            rejection_rate = (
                rejections / decisions if decisions else 0.0
            )

            print(
                f"{regime},{decisions},{proposals},{rejections},"
                f"{trades},{win_rate:.2%},{avg_pnl:.2f},"
                f"{profit_factor:.2f},{proposal_rate:.2%},"
                f"{rejection_rate:.2%},{coverage_tier(trades)}"
            )

        missing = sorted(
            required_regimes - set(stats)
        )

        if missing:
            print("\nMissing required coverage:")
            for regime in missing:
                print(f"- {regime}: INSUFFICIENT")
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())