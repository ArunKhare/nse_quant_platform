"""Build daily realized-volatility observations from 1-minute candles."""

from __future__ import annotations

import argparse
import math

import pandas as pd

from nse_quant.core.constants import TRADING_DAYS_PER_YEAR
from nse_quant.persistence.duckdb_store import DuckDBStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--instrument-token", type=int, default=256265)
    args = parser.parse_args()

    store = DuckDBStore()

    frame = store.read_spot_candles(
        symbol=args.symbol,
        interval="1m",
    )

    if frame.empty:
        raise SystemExit("No 1-minute candles found")

    frame["ts"] = pd.to_datetime(frame["ts"])
    frame["trading_date"] = frame["ts"].dt.date
    frame["return"] = frame.groupby("trading_date")["close"].pct_change()

    written = 0

    for trading_date, group in frame.groupby("trading_date"):
        returns = group["return"].dropna()

        if len(returns) < 2:
            continue

        rv = float(returns.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))

        written += store.write_daily_rv_observation(
            symbol=args.symbol,
            trading_date=trading_date,
            rv=rv,
            observation_count=len(returns),
        )

    print(f"Built {written} daily RV observations")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
