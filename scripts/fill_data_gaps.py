"""Identify and fill historical NIFTY spot-candle gaps from Kite."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from nse_quant.core.settings import get_settings
from nse_quant.integrations.kite_session import get_cached_kite
from nse_quant.market_data.kite_provider import KiteMarketDataProvider
from nse_quant.persistence.duckdb_store import DuckDBStore

IST = ZoneInfo("Asia/Kolkata")

KITE_INTERVALS = {
    "1m": "minute",
    "3m": "3minute",
    "5m": "5minute",
    "10m": "10minute",
    "15m": "15minute",
    "30m": "30minute",
    "60m": "60minute",
    "1d": "day",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Identify and fill historical spot-candle gaps")

    parser.add_argument(
        "--symbol",
        default="NIFTY",
        help="Underlying symbol",
    )

    parser.add_argument(
        "--from",
        dest="from_date",
        required=True,
        help="Start date in YYYY-MM-DD format",
    )

    parser.add_argument(
        "--to",
        dest="to_date",
        required=True,
        help="End date in YYYY-MM-DD format",
    )

    parser.add_argument(
        "--interval",
        default="1m",
        choices=["1m", "3m", "5m", "10m", "15m", "30m", "60m", "1d"],
        help="Storage candle interval to repair",
    )

    parser.add_argument(
        "--min-candles",
        type=int,
        default=1,
        help=(
            "Minimum expected candles per trading day; days below this are treated as incomplete"
        ),
    )

    return parser.parse_args()


def trading_days(
    start_date: date,
    end_date: date,
) -> list[date]:
    days: list[date] = []
    current = start_date

    while current <= end_date:
        if current.weekday() < 5:
            days.append(current)

        current = date.fromordinal(current.toordinal() + 1)

    return days


def main() -> int:
    args = parse_args()
    settings = get_settings()

    start_date = date.fromisoformat(args.from_date)
    end_date = date.fromisoformat(args.to_date)

    if end_date < start_date:
        raise ValueError("--to must be on or after --from")

    kite_interval = KITE_INTERVALS[args.interval]

    store = DuckDBStore()
    kite = get_cached_kite(settings=settings)
    provider = KiteMarketDataProvider(kite)

    provider.underlying = args.symbol

    try:
        spot_token = provider.resolve_spot_instrument_token(args.symbol)

        print(
            "Spot instrument token:",
            args.symbol,
            spot_token,
        )

        print(
            "Storage interval:",
            args.interval,
            "Kite interval:",
            kite_interval,
        )

        existing = {
            row[0]: int(row[1])
            for row in store.conn.execute(
                """
                SELECT
                    CAST(ts AS DATE) AS trading_date,
                    count(*) AS candle_count
                FROM spot_candles
                WHERE symbol = ?
                  AND instrument_token = ?
                  AND interval = ?
                  AND CAST(ts AS DATE) BETWEEN ? AND ?
                GROUP BY CAST(ts AS DATE)
                """,
                [
                    args.symbol,
                    spot_token,
                    args.interval,
                    start_date,
                    end_date,
                ],
            ).fetchall()
        }

        repaired_dates: list[date] = []

        for trading_day in trading_days(start_date, end_date):
            candle_count = existing.get(trading_day, 0)

            if candle_count >= args.min_candles:
                print(f"{trading_day}: OK ({candle_count} {args.interval} candles)")
                continue

            print(f"{trading_day}: GAP ({candle_count} {args.interval} candles found)")

            from_dt = datetime.combine(
                trading_day,
                time(9, 15),
                tzinfo=IST,
            )

            to_dt = datetime.combine(
                trading_day,
                time(15, 30),
                tzinfo=IST,
            )

            try:
                candles = provider.get_historical_candles(
                    symbol=args.symbol,
                    interval=args.interval,
                    from_dt=from_dt,
                    to_dt=to_dt,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"{trading_day}: Kite download failed: {exc}")
                continue

            if not candles:
                print(f"{trading_day}: No historical candles returned by Kite")
                continue

            rows_written = store.write_spot_candles(
                candles=candles,
                symbol=args.symbol,
                instrument_token=spot_token,
                interval=args.interval,
            )

            repaired_dates.append(trading_day)

            print(f"{trading_day}: downloaded={len(candles)} persisted={rows_written}")

        print()
        print("Gap-fill summary")
        print(f"Range: {start_date} to {end_date}")
        print(f"Interval: {args.interval}")
        print(f"Dates repaired: {len(repaired_dates)}")

        for trading_day in repaired_dates:
            print(f"  - {trading_day}")

        return 0

    finally:
        store.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
