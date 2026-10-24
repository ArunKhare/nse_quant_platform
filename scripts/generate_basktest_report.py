from __future__ import annotations

import argparse
from pathlib import Path

from nse_quant.research.backtest.report import generate_backtest_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a QuantStats report for a completed backtest run.",
    )

    parser.add_argument(
        "--run-id",
        required=True,
        help="Backtest run ID under --backtest-dir.",
    )
    parser.add_argument(
        "--backtest-dir",
        default="data/research/backtests",
        help="Directory containing backtest run outputs.",
    )
    parser.add_argument(
        "--risk-free-rate",
        type=float,
        default=0.0,
        help="Annualized risk-free rate used for Sharpe and Sortino.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    run_dir = Path(args.backtest_dir) / args.run_id
    report_path, summary_path = generate_backtest_report(
        run_dir=run_dir,
        risk_free_rate=args.risk_free_rate,
    )

    print("Backtest report generated")
    print(f"Report: {report_path}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
