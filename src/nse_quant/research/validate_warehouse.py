"""Validate partitioned historical option-stream Parquet exports."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Parquet warehouse files"
    )

    parser.add_argument(
        "--warehouse-dir",
        default="data/exports",
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

    return parser.parse_args()


def validate_file(
    path: Path,
    *,
    underlying: str,
    min_snapshots: int,
) -> dict[str, object]:
    result: dict[str, object] = {
        "file": str(path),
        "status": "ok",
        "issues": [],
    }

    if path.stat().st_size == 0:
        result["status"] = "invalid"
        result["issues"].append("zero_byte_file")
        return result

    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        result["status"] = "invalid"
        result["issues"].append(f"unreadable: {exc}")
        return result

    required = {
        "ts",
        "underlying",
        "expiry",
        "strike",
        "option_type",
        "ltp",
        "spot",
    }

    missing = required.difference(frame.columns)

    if missing:
        result["status"] = "invalid"
        result["issues"].append(
            f"missing_columns: {sorted(missing)}"
        )
        return result

    if frame.empty:
        result["status"] = "warning"
        result["issues"].append("empty_file")
        return result

    if not (frame["underlying"] == underlying).all():
        result["status"] = "warning"
        result["issues"].append("unexpected_underlying")

    snapshots = frame["ts"].nunique()
    result["snapshots"] = int(snapshots)

    if snapshots < min_snapshots:
        result["status"] = "warning"
        result["issues"].append(
            f"low_snapshot_count: {snapshots} < {min_snapshots}"
        )

    iv_coverage = (
        frame["iv"].notna().mean()
        if "iv" in frame.columns
        else 0.0
    )

    result["iv_coverage"] = round(float(iv_coverage), 4)

    if iv_coverage < 0.80:
        result["status"] = "warning"
        result["issues"].append(
            f"low_iv_coverage: {iv_coverage:.2%}"
        )

    duplicate_rows = int(frame.duplicated().sum())

    if duplicate_rows:
        result["status"] = "warning"
        result["issues"].append(
            f"duplicate_rows: {duplicate_rows}"
        )

    return result


def main() -> int:
    args = parse_args()

    warehouse = Path(args.warehouse_dir)
    pattern = (
        f"underlying={args.underlying}/year=*/month=*"
        "/option_stream_*.parquet"
    )

    files = sorted(warehouse.glob(pattern))

    if not files:
        print(
            f"No warehouse files found for {args.underlying} "
            f"in {warehouse}"
        )
        return 0

    results = [
        validate_file(
            path,
            underlying=args.underlying,
            min_snapshots=args.min_snapshots,
        )
        for path in files
    ]

    report_frame = pd.DataFrame(results)
    print(report_frame.to_string(index=False))

    invalid = (report_frame["status"] == "invalid").sum()
    warnings = (report_frame["status"] == "warning").sum()

    print(
        f"\nValidated {len(results)} files: "
        f"ok={len(results) - invalid - warnings}, "
        f"warnings={warnings}, invalid={invalid}"
    )

    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())