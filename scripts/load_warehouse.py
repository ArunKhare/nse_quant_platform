"""Load historical option-stream Parquet data for research."""

from __future__ import annotations

import argparse

from nse_quant.core.settings import get_settings
from nse_quant.research.parquet_warehouse import ParquetWarehouse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load partitioned option-stream Parquet data"
    )

    parser.add_argument(
        "--underlying",
        default="NIFTY",
    )

    parser.add_argument(
        "--start",
        required=True,
        help="Start date, YYYY-MM-DD",
    )

    parser.add_argument(
        "--end",
        required=True,
        help="End date, YYYY-MM-DD",
    )

    parser.add_argument(
        "--warehouse-dir",
        default=None,
        help="Parquet warehouse directory",
    )

    parser.add_argument(
        "--output",
        default=None,
        help="Optional output CSV path",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()

    warehouse_dir = (
        args.warehouse_dir
        or settings.storage.parquet_dir
    )

    warehouse = ParquetWarehouse(warehouse_dir)

    frame = warehouse.load_option_stream(
        underlying=args.underlying,
        start_date=args.start,
        end_date=args.end,
    )

    print(
        {
            "underlying": args.underlying,
            "start": args.start,
            "end": args.end,
            "rows": len(frame),
            "snapshots": (
                frame["ts"].nunique() if not frame.empty else 0
            ),
        }
    )

    if args.output:
        frame.to_csv(args.output, index=False)
        print(f"Saved: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())