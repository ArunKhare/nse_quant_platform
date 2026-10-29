"""registered walk-forward runs can be filtered and ranked without
manually inspecting the registry"""

from __future__ import annotations

import argparse
from pathlib import Path

from nse_quant.research.backtest_reporting import compare_experiments


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare registered walk-forward experiments.",
    )

    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("data/research/experiments/experiment_index.csv"),
    )
    parser.add_argument(
        "--min-trades",
        type=int,
        default=20,
        help="Minimum out-of-sample trades required for eligibility.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/research/experiments/comparison.csv"),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    eligible = compare_experiments(
        registry_path=args.registry,
        min_trades=args.min_trades,
        output_path=args.output,
    )

    print(f"Eligible experiments: {len(eligible)}")
    print(f"Comparison written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
