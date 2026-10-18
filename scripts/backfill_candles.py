"""Backfill explicit historical candle ranges in Kite-sized chunks."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from nse_quant.core.settings import get_settings
from nse_quant.integrations.kite_session import get_cached_kite
from nse_quant.market_data.kite_provider import KiteMarketDataProvider
from nse_quant.persistence.duckdb_store import DuckDBStore


KITE_MAX_RANGE_DAYS = {
    "1m": 60,
    "15m": 200,
    "60m": 400,
    "day": 2000,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill NSE spot candles in Kite request chunks"
    )

    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", required=True)
    parser.add_argument("--from", dest="from_dt", required=True)
    parser.add_argument("--to", dest="to_dt", required=True)

    return parser.parse_args()


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def chunk_bounds(
    start: datetime,
    end: datetime,
    max_days: int,
) -> list[tuple[datetime, datetime]]:
    if end <= start:
        raise ValueError("--to must be later than --from")

    chunks: list[tuple[datetime, datetime]] = []
    cursor = start
    step = timedelta(days=max_days)

    while cursor < end:
        chunk_end = min(cursor + step, end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end

    return chunks


def main() -> int:
    args = parse_args()
    settings = get_settings()

    interval = args.interval
    if interval not in settings.market_data.candle_intervals:
        raise ValueError(f"Unsupported interval: {interval!r}")

    max_days = KITE_MAX_RANGE_DAYS.get(interval)
    if max_days is None:
        raise ValueError(f"No Kite chunk limit configured for {interval!r}")

    start_dt = parse_datetime(args.from_dt)
    end_dt = parse_datetime(args.to_dt)

    kite = get_cached_kite(settings=settings)
    provider = KiteMarketDataProvider(kite=kite, underlying=args.symbol)
    store = DuckDBStore()

    instrument_token = provider.resolve_spot_instrument_token(args.symbol)
    print(f"{args.symbol}: instrument_token={instrument_token}")

    try:
        for chunk_start, chunk_end in chunk_bounds(
            start_dt,
            end_dt,
            max_days,
        ):
            candles = provider.get_historical_candles(
                symbol=args.symbol,
                interval=interval,
                from_dt=chunk_start,
                to_dt=chunk_end,
            )

            rows = store.write_spot_candles(
                candles=candles,
                symbol=args.symbol,
                instrument_token=instrument_token,
                interval=interval,
            )

            print(
                f"{args.symbol} {interval} "
                f"{chunk_start.isoformat()} -> {chunk_end.isoformat()}: "
                f"fetched={len(candles)} persisted={rows}"
            )
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())