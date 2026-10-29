"""Inspect DuckDB and Parquet-warehouse data coverage.

Reports candle, RV, IV, option-stream, and warehouse coverage so you can
determine whether enough history exists for research and walk-forward
validation.
uv run python scripts/inspect_data_coverage.py

Or restrict the warehouse report:

powershell
uv run python scripts/inspect_data_coverage.py `
  --underlying NIFTY `
  --start-date 2026-10-29 `
  --end-date 2026-10-29 `
  --min-snapshots 30 `
  --min-iv-coverage 0.80

"""

from __future__ import annotations

import argparse
from pathlib import Path

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.warehouse_validation import validate_warehouse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect database and warehouse data coverage",
    )

    parser.add_argument(
        "--warehouse-dir",
        type=Path,
        default=Path("data/exports"),
    )

    parser.add_argument("--underlying", default="NIFTY")

    parser.add_argument(
        "--start-date",
        default=None,
        help="Optional warehouse filter: YYYY-MM-DD",
    )

    parser.add_argument(
        "--end-date",
        default=None,
        help="Optional warehouse filter: YYYY-MM-DD",
    )

    parser.add_argument(
        "--min-snapshots",
        type=int,
        default=30,
    )

    parser.add_argument(
        "--min-iv-coverage",
        type=float,
        default=0.80,
    )

    return parser.parse_args()


def print_section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def inspect_database(store: DuckDBStore) -> None:
    print_section("DuckDB tables")

    tables = [row[0] for row in store.conn.execute("SHOW TABLES").fetchall()]

    print(f"Tables: {', '.join(tables) if tables else 'none'}")

    for table in tables:
        count = store.conn.execute(
            f"SELECT COUNT(*) FROM {table}",  # noqa: S608
        ).fetchone()[0]
        print(f"  {table}: {count:,} rows")

    print_section("Candle coverage")

    candles = store.conn.execute(
        """
        SELECT
            symbol,
            interval,
            COUNT(*) AS rows,
            COUNT(DISTINCT CAST(ts AS DATE)) AS days,
            MIN(CAST(ts AS DATE)) AS first_date,
            MAX(CAST(ts AS DATE)) AS last_date
        FROM spot_candles
        GROUP BY symbol, interval
        ORDER BY symbol, interval
        """,
    ).fetchdf()

    print(candles.to_string(index=False))

    print_section("Daily RV coverage")

    rv = store.conn.execute(
        """
        SELECT
            symbol,
            COUNT(*) AS observations,
            COUNT(DISTINCT CAST(trading_date AS DATE)) AS days,
            MIN(CAST(trading_date AS DATE)) AS first_date,
            MAX(CAST(trading_date AS DATE)) AS last_date
        FROM daily_rv_observations
        GROUP BY symbol
        ORDER BY symbol
        """,
    ).fetchdf()

    print(rv.to_string(index=False))

    print_section("Underlying IV coverage")

    iv = store.conn.execute(
        """
        SELECT
            underlying,
            COUNT(*) AS observations,
            COUNT(DISTINCT CAST(ts AS DATE)) AS days,
            MIN(CAST(ts AS DATE)) AS first_date,
            MAX(CAST(ts AS DATE)) AS last_date
        FROM underlying_iv_observations
        GROUP BY underlying
        ORDER BY underlying
        """,
    ).fetchdf()

    print(iv.to_string(index=False))

    print_section("IV-RV aligned days")

    aligned = store.conn.execute(
        """
        SELECT COUNT(*) AS aligned_days
        FROM (
            SELECT DISTINCT CAST(iv.ts AS DATE) AS trading_date
            FROM underlying_iv_observations iv
            INNER JOIN daily_rv_observations rv
                ON rv.symbol = iv.underlying
                AND CAST(rv.trading_date AS DATE) = CAST(iv.ts AS DATE)
        )
        """,
    ).fetchone()[0]

    print(f"IV-RV aligned days: {aligned}")

    print_section("Option-stream coverage")

    option_stream = store.conn.execute(
        """
        SELECT
            underlying,
            COUNT(*) AS rows,
            COUNT(DISTINCT CAST(ts AS DATE)) AS days,
            MIN(CAST(ts AS DATE)) AS first_date,
            MAX(CAST(ts AS DATE)) AS last_date
        FROM option_stream
        GROUP BY underlying
        ORDER BY underlying
        """,
    ).fetchdf()

    print(option_stream.to_string(index=False))


def inspect_warehouse(
    *,
    warehouse_dir: Path,
    underlying: str,
    start_date: str | None,
    end_date: str | None,
    min_snapshots: int,
    min_iv_coverage: float,
) -> None:
    print_section("Parquet warehouse validation")

    validation = validate_warehouse(
        warehouse_dir,
        underlying=underlying,
        min_snapshots=min_snapshots,
        min_iv_coverage=min_iv_coverage,
    )

    if start_date:
        validation = validation[
            validation["file"].str.contains(
                f"option_stream_{start_date}",
                na=False,
            )
            | (
                validation["file"].str.extract(
                    r"option_stream_(\d{4}-\d{2}-\d{2})",
                )[0]
                >= start_date
            )
        ]

    if end_date:
        extracted = validation["file"].str.extract(
            r"option_stream_(\d{4}-\d{2}-\d{2})",
        )[0]
        validation = validation[extracted <= end_date]

    print(validation.to_string(index=False))

    valid = validation[validation["status"] == "ok"]

    print(
        f"\nResearch-grade days: {len(valid)} of {len(validation)} warehouse files",
    )

    if not valid.empty:
        print(
            "Research-grade date range: "
            f"{valid['file'].str.extract(r'option_stream_(\d{4}-\d{2}-\d{2})')[0].min()} "
            "to "
            f"{valid['file'].str.extract(r'option_stream_(\d{4}-\d{2}-\d{2})')[0].max()}",
        )


def main() -> int:
    args = parse_args()

    store = DuckDBStore()

    try:
        inspect_database(store)
    finally:
        store.conn.close()

    inspect_warehouse(
        warehouse_dir=args.warehouse_dir,
        underlying=args.underlying,
        start_date=args.start_date,
        end_date=args.end_date,
        min_snapshots=args.min_snapshots,
        min_iv_coverage=args.min_iv_coverage,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
