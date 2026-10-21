"""Aggregate persisted 1-minute spot candles into daily OHLCV candles."""

from __future__ import annotations

import argparse

from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build daily candles from 1-minute candles"
    )

    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = DuckDBStore()

    try:
        # Replace any previously aggregated daily candles in the range.
        store.conn.execute(
            """
            DELETE FROM spot_candles
            WHERE symbol = ?
              AND interval = 'day'
              AND CAST(ts AS DATE) BETWEEN ? AND ?
            """,
            [args.symbol, args.start_date, args.end_date],
        )

        instrument_token = store.conn.execute(
            """
            SELECT instrument_token
            FROM spot_candles
            WHERE symbol = ?
              AND interval = '1m'
            ORDER BY ts DESC
            LIMIT 1
            """,
            [args.symbol],
        ).fetchone()

        if instrument_token is None:
            print(f"No 1-minute candles found for {args.symbol}")
            return 1

        store.conn.execute(
            """
            INSERT INTO spot_candles
            SELECT
                symbol,
                instrument_token,
                date_trunc('day', ts) AS ts,
                'day' AS interval,
                arg_min(open, ts) AS open,
                max(high) AS high,
                min(low) AS low,
                arg_max(close, ts) AS close,
                COALESCE(sum(volume), 0) AS volume,
                arg_max(oi, ts) AS oi
            FROM spot_candles
            WHERE symbol = ?
              AND interval = '1m'
              AND CAST(ts AS DATE) BETWEEN ? AND ?
            GROUP BY
                symbol,
                instrument_token,
                date_trunc('day', ts)
            """,
            [
                args.symbol,
                args.start_date,
                args.end_date,
            ],
        )

        daily_count_row = store.conn.execute(
            """
            SELECT COUNT(*)
            FROM spot_candles
            WHERE symbol = ?
              AND interval = 'day'
              AND CAST(ts AS DATE) BETWEEN ? AND ?
            """,
            [
                args.symbol,
                args.start_date,
                args.end_date,
            ],
        ).fetchone()
        daily_count = daily_count_row[0] if daily_count_row is not None else 0

        print(
            f"{args.symbol}: built {daily_count} daily candles "
            f"from 1m data between {args.start_date} "
            f"and {args.end_date}"
        )

        return 0

    finally:
        store.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())