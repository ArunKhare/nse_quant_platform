from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


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


def count_warehouse_days(warehouse_dir: Path) -> int:
    return len(list(warehouse_dir.glob("**/option_stream_*.parquet")))


def latest_experiment(registry_path: Path) -> dict[str, object] | None:
    if not registry_path.exists():
        return None

    registry = pd.read_csv(registry_path)

    if registry.empty:
        return None

    latest = registry.sort_values("registered_at").iloc[-1]
    return latest.to_dict()


def main() -> int:
    args = parse_args()

    readiness = {}
    if args.readiness.exists():
        readiness = json.loads(args.readiness.read_text(encoding="utf-8"))

    latest_experiment_row = latest_experiment(args.registry)
    warehouse_days = count_warehouse_days(args.warehouse_dir)

    digest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "warehouse_option_stream_days": warehouse_days,
        "readiness": readiness,
        "latest_experiment": latest_experiment_row,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(digest, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"Research status digest written: {args.output}")
    print(f"Warehouse option-stream days: {warehouse_days}")

    if latest_experiment_row:
        print(
            "Latest experiment: "
            f"{latest_experiment_row['run_id']} | "
            f"trades={latest_experiment_row['out_of_sample_trades']} | "
            f"pnl={latest_experiment_row['out_of_sample_pnl']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
