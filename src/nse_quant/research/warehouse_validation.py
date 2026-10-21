"""Validation utilities for partitioned Parquet warehouse exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
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
    """Validate one option-stream Parquet export using DuckDB."""

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

    parquet_path = path.as_posix()

    conn = duckdb.connect()

    try:
        columns = {
            row[0]
            for row in conn.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{parquet_path}')"
            ).fetchall()
        }

        missing = REQUIRED_COLUMNS.difference(columns)

        if missing:
            result["status"] = "invalid"
            result["issues"].append(
                f"missing_columns: {sorted(missing)}"
            )
            return result

        stats = conn.execute(
            f"""
            SELECT
                count(*) AS rows,
                count(DISTINCT ts) AS snapshots,
                count(*) FILTER (WHERE iv IS NOT NULL) AS iv_rows,
                count(*) FILTER (
                    WHERE underlying <> ?
                ) AS unexpected_underlying_rows
            FROM read_parquet('{parquet_path}')
            """,
            [underlying],
        ).fetchone()

        if stats is None:
            result["status"] = "invalid"
            result["issues"].append("statistics_query_returned_no_result")
            return result

        row_count, snapshot_count, iv_rows, unexpected = stats

        result["rows"] = int(row_count)
        result["snapshots"] = int(snapshot_count)

        if row_count == 0:
            result["status"] = "invalid"
            result["issues"].append("empty_file")
            return result

        if unexpected:
            result["status"] = "warning"
            result["issues"].append("unexpected_underlying")

        iv_coverage = (
            float(iv_rows) / float(row_count) if row_count else 0.0
        )
        result["iv_coverage"] = round(iv_coverage, 4)

        if snapshot_count < min_snapshots:
            result["status"] = "warning"
            result["issues"].append(
                f"low_snapshot_count: {snapshot_count} "
                f"< {min_snapshots}"
            )

        if iv_coverage < min_iv_coverage:
            result["status"] = "warning"
            result["issues"].append(
                f"low_iv_coverage: {iv_coverage:.2%}"
            )

        duplicate_result = conn.execute(
            f"""
            SELECT count(*)
            FROM (
                SELECT
                    *,
                    row_number() OVER (
                        PARTITION BY
                            run_id,
                            ts,
                            underlying,
                            expiry,
                            strike,
                            option_type,
                            tradingsymbol
                        ORDER BY ts
                    ) AS row_number
                FROM read_parquet('{parquet_path}')
            )
            WHERE row_number > 1
            """
        ).fetchone()
        duplicate_rows = duplicate_result[0] if duplicate_result else 0

        if duplicate_rows:
            result["status"] = "warning"
            result["issues"].append(
                f"duplicate_rows: {duplicate_rows}"
            )

        return result

    except Exception as exc:  # noqa: BLE001
        result["status"] = "invalid"
        result["issues"].append(f"unreadable: {exc}")
        return result

    finally:
        conn.close()


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