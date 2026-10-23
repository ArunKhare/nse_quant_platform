"""Backfill partitioned market-regime Parquet exports."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from nse_quant.persistence.duckdb_store import DuckDBStore


def build_regime_export_path(
    *,
    export_dir: Path,
    underlying: str,
    trading_date: date,
) -> Path:
    return (
        export_dir
        / f"underlying={underlying}"
        / f"year={trading_date.year}"
        / f"month={trading_date.month:02d}"
        / f"market_regime_{trading_date.isoformat()}.parquet"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill market-regime Parquet exports")

    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=Path("data/exports"),
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Inclusive start date, YYYY-MM-DD",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="Inclusive end date, YYYY-MM-DD",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = DuckDBStore()

    try:
        rows = store.conn.execute(
            """
            SELECT CAST(ts AS DATE) AS trading_date
            FROM market_regimes
            WHERE symbol = ?
              AND CAST(ts AS DATE) BETWEEN ? AND ?
            GROUP BY 1
            ORDER BY 1
            """,
            [
                args.symbol,
                args.start_date,
                args.end_date,
            ],
        ).fetchall()

        exported = 0

        for (trading_date,) in rows:
            output_path = build_regime_export_path(
                export_dir=args.export_dir,
                underlying=args.symbol,
                trading_date=trading_date,
            )

            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            store.export_market_regime_parquet(
                output_path=output_path,
                underlying=args.symbol,
                date_str=trading_date.isoformat(),
            )

            print(f"Exported {trading_date}: {output_path}")
            exported += 1

        print(f"Exported regime days: {exported}")
        return 0

    finally:
        store.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
