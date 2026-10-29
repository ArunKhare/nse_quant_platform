"""daily research status digest. acquisition, backtesting, reporting,
registry, and comparison layers are complete; this adds one consolidated
daily health/status artifact so you can immediately see whether data
collection and research runs are healthy
"""

from __future__ import annotations

import argparse
from pathlib import Path

from nse_quant.research.backtest_reporting import generate_digest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a consolidated daily research status digest.",
    )

    parser.add_argument(
        "--readiness",
        type=Path,
        default=Path("data/research/backtest_readiness.json"),
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("data/research/experiments/experiment_index.csv"),
    )
    parser.add_argument(
        "--warehouse-dir",
        type=Path,
        default=Path("data/exports"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/research/daily_status/daily_status.json"),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    digest = generate_digest(
        readiness_path=args.readiness,
        registry_path=args.registry,
        warehouse_dir=args.warehouse_dir,
        output_path=args.output,
    )

    print(f"Research status digest written: {args.output}")
    print(f"Warehouse option-stream days: {digest['warehouse_option_stream_days']}")

    if digest["latest_experiment"]:
        latest = digest["latest_experiment"]
        print(
            "Latest experiment: "
            f"{latest['run_id']} | "
            f"trades={latest['out_of_sample_trades']} | "
            f"pnl={latest['out_of_sample_pnl']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
