"""Import NIFTY historical candles into DuckDB."""

from __future__ import annotations

import argparse
from datetime import datetime

from nse_quant.core.settings import get_settings
from nse_quant.integrations.kite_session import get_cached_kite
from nse_quant.market_data.historical_candles import (
    HistoricalCandleImporter,
)
from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import NIFTY historical candles"
    )

    parser.add_argument(
        "--start",
        required=True,
        help="Start date, e.g. 2026-10-01",
    )

    parser.add_argument(
        "--end",
        required=True,
        help="End date, e.g. 2026-10-17",
    )

    parser.add_argument(
        "--interval",
        default="minute",
        choices=[
            "minute",
            "3minute",
            "5minute",
            "10minute",
            "15minute",
            "30minute",
            "60minute",
            "day",
        ],
    )

    parser.add_argument(
        "--instrument-token",
        type=int,
        default=256265,
        help="Kite instrument token; 256265 is NIFTY 50 index",
    )

    parser.add_argument(
        "--symbol",
        default="NIFTY 50",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()

    kite = get_cached_kite(settings=settings)
    store = DuckDBStore()

    importer = HistoricalCandleImporter(kite, store)

    rows = importer.import_candles(
        instrument_token=args.instrument_token,
        symbol=args.symbol,
        start=datetime.fromisoformat(args.start),
        end=datetime.fromisoformat(args.end),
        interval=args.interval,
    )

    print(f"Imported {rows} candles.")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
