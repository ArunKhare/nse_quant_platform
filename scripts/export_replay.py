"""Export recent market snapshots for decision-loop replay."""

from __future__ import annotations

import argparse

from nse_quant.market_data.replay_exporter import ReplayExporter
from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export recent NIFTY snapshots for replay"
    )

    parser.add_argument(
        "--underlying",
        default="NIFTY",
    )

    parser.add_argument(
        "--minutes",
        type=int,
        default=30,
        help="Export snapshots from the last N minutes",
    )

    parser.add_argument(
        "--output",
        default="data/replay/replay.json",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    store = DuckDBStore()
    exporter = ReplayExporter(store)

    output = exporter.export_recent_snapshots(
        underlying=args.underlying,
        output_path=args.output,
        minutes=args.minutes,
    )

    print(f"Replay exported: {output}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
