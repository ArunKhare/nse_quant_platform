from __future__ import annotations

import argparse
from pathlib import Path

from nse_quant.research.backtest.experiment_analysis import save_analysis_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze and rank paper-only backtest parameter experiments.",
    )

    parser.add_argument(
        "--results",
        required=True,
        help="Path to parameter_experiments.csv.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for ranking and analysis outputs.",
    )
    parser.add_argument(
        "--min-trades",
        type=int,
        default=10,
        help="Minimum closed trades required for promotion eligibility.",
    )
    parser.add_argument(
        "--min-snapshots",
        type=int,
        default=500,
        help="Minimum snapshots required for promotion eligibility.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    ranked_path, report_path = save_analysis_report(
        results_path=Path(args.results),
        output_dir=Path(args.output_dir),
        min_trades=args.min_trades,
        min_snapshots=args.min_snapshots,
    )

    print("Experiment analysis complete")
    print(f"Ranking: {ranked_path}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
