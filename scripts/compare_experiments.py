from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare registered backtest experiments.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("data/research/experiments/experiment_index.csv"),
    )
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/research/experiments/comparison.csv"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.registry.exists():
        raise FileNotFoundError(f"Experiment registry not found: {args.registry}")

    registry = pd.read_csv(args.registry)
    eligible = registry[registry["out_of_sample_trades"] >= args.min_trades]

    eligible = eligible.sort_values(
        ["out_of_sample_pnl", "out_of_sample_trades"],
        ascending=[False, False],
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    eligible.to_csv(args.output, index=False)

    print(f"Registered experiments: {len(registry)}")
    print(f"Eligible experiments: {len(eligible)}")
    print(f"Comparison written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
