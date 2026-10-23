"""Build multi-timeframe spot features from persisted candles."""

from __future__ import annotations

import argparse

import pandas as pd

from nse_quant.core.settings import get_settings
from nse_quant.features.spot_features import SpotFeatureBuilder
from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build multi-timeframe spot features")

    parser.add_argument(
        "--symbol",
        action="append",
        default=None,
        help="Underlying symbol; repeat for multiple symbols",
    )

    parser.add_argument(
        "--from",
        dest="from_ts",
        default=None,
        help="Optional start timestamp in ISO format",
    )

    parser.add_argument(
        "--to",
        dest="to_ts",
        default=None,
        help="Optional end timestamp in ISO format",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()

    symbols = args.symbol or [settings.market_data.default_symbol]
    from_ts = pd.Timestamp(args.from_ts) if args.from_ts else None
    to_ts = pd.Timestamp(args.to_ts) if args.to_ts else None

    if from_ts is not None and from_ts.hour == 0 and from_ts.minute == 0:
        from_ts = from_ts.tz_localize("Asia/Kolkata")

    if to_ts is not None and to_ts.hour == 0 and to_ts.minute == 0:
        to_ts = (to_ts + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)).tz_localize("Asia/Kolkata")

    store = DuckDBStore()

    try:
        builder = SpotFeatureBuilder(store=store)

        for symbol in symbols:
            features = builder.build(
                symbol=symbol,
                from_ts=from_ts,
                to_ts=to_ts,
            )

            rows = store.write_spot_features(features)

            print(f"{symbol}: built={len(features)} persisted={rows}")
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
