"""Backfill partitioned option-stream Parquet exports."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from nse_quant.persistence.duckdb_store import DuckDBStore


def build_option_stream_export_path(
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
        / f"option_stream_{trading_date.isoformat()}.parquet"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill option-stream Parquet exports",
    )

    parser.add_argument("--underlying", default="NIFTY")
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=Path("data/exports"),
    )
    parser.add_argument("--date", required=True, help="Trading date, YYYY-MM-DD")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    trading_date = date.fromisoformat(args.date)
    output_path = build_option_stream_export_path(
        export_dir=args.export_dir,
        underlying=args.underlying,
        trading_date=trading_date,
    )

    store = DuckDBStore()

    try:
        row_count = store.conn.execute(
            """
            SELECT COUNT(*)
            FROM option_stream
            WHERE underlying = ?
              AND CAST(ts AS DATE) = ?
            """,
            [args.underlying, trading_date],
        ).fetchone()[0]

        if row_count == 0:
            print(f"No option_stream rows for {args.underlying} on {trading_date}")
            return 1

        output_path.parent.mkdir(parents=True, exist_ok=True)

        escaped_path = str(output_path).replace("'", "''")

        store.conn.execute(
            f"""
            COPY (
                SELECT
                    run_id,
                    ts,
                    underlying,
                    expiry,
                    strike,
                    option_type,
                    tradingsymbol,
                    instrument_token,
                    lot_size,
                    spot,
                    ltp,
                    bid,
                    ask,
                    volume,
                    oi,
                    iv,
                    delta,
                    gamma,
                    vega,
                    theta,
                    quote_status,
                    payload_json
                FROM option_stream
                WHERE underlying = ?
                  AND CAST(ts AS DATE) = ?
                ORDER BY ts
            )
            TO '{escaped_path}'
            (FORMAT PARQUET, COMPRESSION ZSTD)
            """,
            [args.underlying, trading_date],
        )

        print(f"Exported {row_count} rows: {output_path}")
        return 0

    finally:
        store.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
