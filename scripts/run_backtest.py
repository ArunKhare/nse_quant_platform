from __future__ import annotations

import argparse
from datetime import date, datetime

from nse_quant.research.backtest.config import BacktestConfig
from nse_quant.research.backtest.engine import BacktestEngine

now = datetime.now()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Milestone 2 backtest.")

    parser.add_argument("--warehouse-dir", default="data/exports")
    parser.add_argument("--output-dir", default="data/research/backtests")
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    parser.add_argument("--run-id", type=str, default=None, help="Unique run identifier")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = BacktestConfig(
        warehouse_dir=args.warehouse_dir,
        output_dir=args.output_dir,
        underlying=args.symbol,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        initial_capital=args.initial_capital,
        **({"run_id": args.run_id} if args.run_id else {}),
    )
    engine = BacktestEngine(config)
    result = engine.run()
    output_dir = engine.save(result)

    print("Backtest complete")
    print(f"Snapshots processed: {len(result.decisions)}")
    print(f"Proposals generated: {result.proposal_count}")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
