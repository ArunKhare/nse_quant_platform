"""Validation utilities for partitioned Parquet warehouse exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED_COLUMNS = {
    "ts",
    "underlying",
    "expiry",
    "strike",
    "option_type",
    "ltp",
    "spot",
}


def validate_parquet_file(
    path: str | Path,
    *,
    underlying: str,
    min_snapshots: int = 100,
    min_iv_coverage: float = 0.80,
) -> dict[str, Any]:
    """Validate one option-stream Parquet export."""
    path = Path(path)

    result: dict[str, Any] = {
        "file": str(path),
        "status": "ok",
        "issues": [],
        "rows": 0,
        "snapshots": 0,
        "iv_coverage": 0.0,
    }

    if not path.exists():
        result["status"] = "invalid"
        result["issues"].append("file_missing")
        return result

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

    result["rows"] = len(frame)

    missing = REQUIRED_COLUMNS.difference(frame.columns)

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

    snapshots = int(frame["ts"].nunique())
    result["snapshots"] = snapshots

    if snapshots < min_snapshots:
        result["status"] = "warning"
        result["issues"].append(
            f"low_snapshot_count: {snapshots} < {min_snapshots}"
        )

    if "iv" in frame.columns:
        iv_coverage = float(frame["iv"].notna().mean())
    else:
        iv_coverage = 0.0

    result["iv_coverage"] = round(iv_coverage, 4)

    if iv_coverage < min_iv_coverage:
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


def validate_warehouse(
    warehouse_dir: str | Path,
    *,
    underlying: str,
    min_snapshots: int = 100,
    min_iv_coverage: float = 0.80,
) -> pd.DataFrame:
    """Validate all option-stream Parquet files for one underlying."""
    warehouse_path = Path(warehouse_dir)

    pattern = (
        f"underlying={underlying}/year=*/month=*"
        "/option_stream_*.parquet"
    )

    files = sorted(warehouse_path.glob(pattern))

    if not files:
        return pd.DataFrame(
            columns=[
                "file",
                "status",
                "issues",
                "rows",
                "snapshots",
                "iv_coverage",
            ]
        )

    results = [
        validate_parquet_file(
            path,
            underlying=underlying,
            min_snapshots=min_snapshots,
            min_iv_coverage=min_iv_coverage,
        )
        for path in files
    ]

    return pd.DataFrame(results)