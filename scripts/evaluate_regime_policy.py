"""Evaluate the configured iron-condor regime policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nse_quant.core.settings import get_settings
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.regime_policy_evaluation import evaluate_regime_policy, export_evaluation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the configured regime policy for a strategy"
        )
    )

    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument(
        "--strategy",
        default="iron_condor_monitor",
    )
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--min-trades-per-regime",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Write the effective policy to data/active_regime_policy.json",
    )
    parser.add_argument(
        "--output",
        default="data/active_regime_policy.json",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    store = DuckDBStore(read_only=True)

    try:
        evaluation, _outcomes = evaluate_regime_policy(
            settings,
            symbol=args.symbol,
            strategy_id=args.strategy,
            start_date=args.start,
            end_date=args.end,
            min_trades_per_regime=args.min_trades_per_regime,
        )

        print(json.dumps(evaluation.__dict__, indent=2, default=str))

        if args.export:
            export_evaluation(
                evaluation,
                Path(args.output),
            )
            print(f"\nExported policy: {args.output}")

        return 0 if evaluation.actionable else 2

    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())