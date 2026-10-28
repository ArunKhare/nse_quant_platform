"""Build intraday spot candles from persisted 1-minute candles.

Supported intervals: 5m, 15m, 30m, 60m.
"""

from __future__ import annotations

import argparse

from nse_quant.persistence.duckdb_store import DuckDBStore

INTERVALS = {
    "5m": "5 minutes",
    "15m": "15 minutes",
    "30m": "30 minutes",
    "60m": "60 minutes",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build intraday candles from 1-minute candles",
    )

    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument(
        "--intervals",
        default="5m,15m,30m,60m",
        help="Comma-separated intervals: 5m,15m,30m,60m",
    )

    return parser.parse_args()


def build_interval_candles(
    *,
    store: DuckDBStore,
    symbol: str,
    trade_date: str,
    interval: str,
) -> int:
    if interval not in INTERVALS:
        raise ValueError(
            f"Unsupported interval: {interval}. Supported intervals: {', '.join(INTERVALS)}",
        )

    bucket = INTERVALS[interval]

    store.conn.execute(
        """
        DELETE FROM spot_candles
        WHERE symbol = ?
          AND interval = ?
          AND CAST(ts AS DATE) = ?
        """,
        [symbol, interval, trade_date],
    )

    store.conn.execute(
        f"""
        INSERT INTO spot_candles (
            symbol,
            instrument_token,
            ts,
            interval,
            open,
            high,
            low,
            close,
            volume,
            oi
        )
        SELECT
            symbol,
            instrument_token,
            time_bucket(INTERVAL '{bucket}', ts) AS ts,
            ? AS interval,
            arg_min(open, ts) AS open,
            max(high) AS high,
            min(low) AS low,
            arg_max(close, ts) AS close,
            COALESCE(sum(volume), 0) AS volume,
            arg_max(oi, ts) AS oi
        FROM spot_candles
        WHERE symbol = ?
          AND interval = '1m'
          AND CAST(ts AS DATE) = ?
        GROUP BY
            symbol,
            instrument_token,
            time_bucket(INTERVAL '{bucket}', ts)
        """,
        [interval, symbol, trade_date],
    )

    count = store.conn.execute(
        """
        SELECT COUNT(*)
        FROM spot_candles
        WHERE symbol = ?
          AND interval = ?
          AND CAST(ts AS DATE) = ?
        """,
        [symbol, interval, trade_date],
    ).fetchone()[0]

    return int(count)


def main() -> int:
    args = parse_args()

    requested_intervals = [value.strip() for value in args.intervals.split(",") if value.strip()]

    store = DuckDBStore()

    try:
        for interval in requested_intervals:
            count = build_interval_candles(
                store=store,
                symbol=args.symbol,
                trade_date=args.trade_date,
                interval=interval,
            )

            print(
                f"{args.symbol}: built {count} {interval} candles for {args.trade_date}",
            )

        return 0
    finally:
        store.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
