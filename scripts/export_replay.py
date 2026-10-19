"""Export recent chain snapshots for deterministic replay."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from nse_quant.market_data.replay_exporter import ReplayExporter
from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export NSE chain snapshots for replay"
    )

    parser.add_argument(
        "--underlying",
        default="NIFTY",
        help="Underlying symbol",
    )

    parser.add_argument(
        "--minutes",
        type=int,
        default=None,
        help="Export snapshots from the last N minutes",
    )

    parser.add_argument(
        "--from",
        dest="from_dt",
        default=None,
        help="Start datetime in ISO format, e.g. 2026-10-16T09:15:00+05:30",
    )

    parser.add_argument(
        "--to",
        dest="to_dt",
        default=None,
        help="End datetime in ISO format, e.g. 2026-10-16T15:30:00+05:30",
    )

    default_output = (
        "data/replays/"
        f"{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        "_replay.json"
    )

    parser.add_argument(
        "--output",
        default=default_output,
        help="Output replay JSON path",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.minutes is None and not (args.from_dt and args.to_dt):
        raise SystemExit(
            "Provide either --minutes or both --from and --to"
        )

    if args.minutes is not None and (args.from_dt or args.to_dt):
        raise SystemExit(
            "Use either --minutes or --from/--to, not both"
        )

    store = DuckDBStore()
    exporter = ReplayExporter(store)

    try:
        if args.minutes is not None:
            output = exporter.export_recent_snapshots(
                underlying=args.underlying,
                output_path=args.output,
                minutes=args.minutes,
            )
        else:
            from_dt = datetime.fromisoformat(args.from_dt)
            to_dt = datetime.fromisoformat(args.to_dt)

            if to_dt <= from_dt:
                raise SystemExit("--to must be later than --from")

            output = exporter.export_snapshots(
                underlying=args.underlying,
                output_path=args.output,
                from_dt=from_dt,
                to_dt=to_dt,
            )

        print(f"Replay exported: {output}")
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())