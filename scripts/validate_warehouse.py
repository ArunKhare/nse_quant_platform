"""Validate partitioned historical option-stream Parquet exports."""

from __future__ import annotations

import argparse

from nse_quant.core.settings import get_settings
from nse_quant.research.warehouse_validation import (
    validate_warehouse,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Parquet warehouse files"
    )

    parser.add_argument(
        "--warehouse-dir",
        default=None,
        help="Parquet warehouse directory",
    )

    parser.add_argument(
        "--underlying",
        default="NIFTY",
    )

    parser.add_argument(
        "--min-snapshots",
        type=int,
        default=100,
        help="Minimum distinct snapshots expected per trading day",
    )

    parser.add_argument(
        "--min-iv-coverage",
        type=float,
        default=0.80,
        help="Minimum fraction of rows with non-null IV",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()

    warehouse_dir = (
        args.warehouse_dir
        or settings.storage.parquet_dir
    )

    report = validate_warehouse(
        warehouse_dir,
        underlying=args.underlying,
        min_snapshots=args.min_snapshots,
        min_iv_coverage=args.min_iv_coverage,
    )

    if report.empty:
        print(
            f"No warehouse files found for {args.underlying} "
            f"in {warehouse_dir}"
        )
        return 0

    print(report.to_string(index=False))

    invalid = int((report["status"] == "invalid").sum())
    warnings = int((report["status"] == "warning").sum())
    ok = int((report["status"] == "ok").sum())

    print(
        f"\nValidated {len(report)} files: "
        f"ok={ok}, warnings={warnings}, invalid={invalid}"
    )

    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())