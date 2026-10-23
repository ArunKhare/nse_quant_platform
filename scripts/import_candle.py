"""Import explicit-date-range NSE spot candles into DuckDB."""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from nse_quant.core.settings import get_settings
from nse_quant.integrations.kite_session import get_cached_kite
from nse_quant.market_data.kite_provider import KiteMarketDataProvider
from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import historical NSE spot candles")

    parser.add_argument(
        "--symbol",
        action="append",
        default=None,
        help="Underlying symbol; repeat for multiple symbols",
    )

    parser.add_argument(
        "--intervals",
        default="1m,15m,60m,day",
        help="Comma-separated candle intervals",
    )

    parser.add_argument(
        "--from",
        dest="from_dt",
        required=True,
        help="Start datetime in ISO format",
    )

    parser.add_argument(
        "--to",
        dest="to_dt",
        required=True,
        help="End datetime in ISO format",
    )

    return parser.parse_args()


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def main() -> None:
    args = parse_args()
    settings = get_settings()

    symbols = args.symbol or [settings.market_data.default_symbol]
    intervals = [interval.strip() for interval in args.intervals.split(",") if interval.strip()]

    start_dt = parse_datetime(args.from_dt)
    end_dt = parse_datetime(args.to_dt)

    if end_dt <= start_dt:
        raise ValueError("--to must be later than --from")

    kite = get_cached_kite(settings=settings)
    provider = KiteMarketDataProvider(kite=kite, underlying=symbols[0])
    store = DuckDBStore()

    try:
        for symbol in symbols:
            instrument_token = provider.resolve_spot_instrument_token(symbol)
            print(f"{symbol}: instrument_token={instrument_token}")

            for interval_key in intervals:
                if interval_key not in settings.market_data.candle_intervals:
                    raise ValueError(f"Unsupported interval: {interval_key!r}")

                candles: list[dict[str, Any]] = provider.get_historical_candles(
                    symbol=symbol,
                    interval=interval_key,
                    from_dt=start_dt,
                    to_dt=end_dt,
                )

                if not candles:
                    print(f"No candles: {symbol} {interval_key}")
                    continue

                rows = store.write_spot_candles(
                    candles=candles,
                    symbol=symbol,
                    instrument_token=instrument_token,
                    interval=interval_key,
                )

                print(f"{symbol} {interval_key}: fetched={len(candles)} persisted={rows}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
