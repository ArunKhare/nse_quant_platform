"""Build point-in-time market regimes from persisted daily data."""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import cast

import pandas as pd

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.regimes import (
    classify_regime,
    rolling_percentile,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build historical market regimes"
    )

    parser.add_argument("--symbol", required=True)
    parser.add_argument("--from", dest="from_ts", required=True)
    parser.add_argument("--to", dest="to_ts", required=True)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = DuckDBStore()

    try:
        daily = store.conn.execute(
            """
            SELECT
                ts,
                close
            FROM spot_candles
            WHERE symbol = ?
              AND interval = 'day'
              AND ts >= ?
              AND ts <= ?
            ORDER BY ts
            """,
            [args.symbol, args.from_ts, args.to_ts],
        ).fetchdf()

        if daily.empty:
            print(f"No daily candles for {args.symbol}")
            return 0

        daily["sma50"] = daily["close"].rolling(50, min_periods=50).mean()
        daily["returns"] = daily["close"].pct_change()
        daily["realized_volatility"] = (
            daily["returns"]
            .rolling(20, min_periods=20)
            .std(ddof=1)
            * (252 ** 0.5)
        )
        daily["rv_percentile"] = rolling_percentile(
            daily["realized_volatility"],
            window=252,
        )

        iv_history = store.conn.execute(
            """
            SELECT
                trading_date,
                AVG(iv) AS atm_iv
            FROM (
                SELECT
                    CAST(ts AS DATE) AS trading_date,
                    iv
                FROM option_stream
                WHERE underlying = ?
                  AND iv IS NOT NULL
                  AND CAST(ts AS DATE) <= ?

                UNION ALL

                SELECT
                    CAST(ts AS DATE) AS trading_date,
                    iv
                FROM underlying_iv_observations
                WHERE underlying = ?
                  AND iv IS NOT NULL
                  AND CAST(ts AS DATE) <= ?
            )
            GROUP BY trading_date
            ORDER BY trading_date
            """,
            [
                args.symbol,
                args.to_ts,
                args.symbol,
                args.to_ts,
            ],
        ).fetchdf()

        print(
            f"IV history days={len(iv_history)}, "
            f"last_date={iv_history['trading_date'].iloc[-1]}"
        )
        iv_percentiles: dict[object, float] = {}

        iv_history["trading_date"] = pd.to_datetime(
            iv_history["trading_date"]

        ).dt.date

        if not iv_history.empty:
            iv_history["iv_rank"] = (
                iv_history["atm_iv"]
                .rolling(252, min_periods=30)
                .apply(
                    lambda values: (
                        (values[-1] > values[:-1]).mean() * 100
                        if len(values) > 1
                        else float("nan")
                    ),
                    raw=True,
                )
            )

            iv_percentiles = {
                row.trading_date: float(cast(float, row.iv_rank))
                for row in iv_history.itertuples()
                if pd.notna(row.iv_rank)
            }

        print(
            "IV rank available dates:",
            len(iv_percentiles),
            "last:",
            max(iv_percentiles) if iv_percentiles else None,
        )

        atr = store.conn.execute(
            """
            SELECT
                ts,
                atr_1m_14
            FROM spot_features
            WHERE symbol = ?
              AND atr_1m_14 IS NOT NULL
            ORDER BY ts
            """,
            [args.symbol],
        ).fetchdf()

        atr_by_date: dict[object, float] = {}

        if not atr.empty:
            atr["trading_date"] = (
                pd.to_datetime(atr["ts"])
                .dt.tz_convert("Asia/Kolkata")
                .dt.date
            )

            latest_atr = atr.groupby("trading_date").last()

            atr_by_date = {
                row.Index: float(cast(float, row.atr_1m_14))
                for row in latest_atr.itertuples()
            }

        written = 0

        for row in daily.itertuples():
            ts = cast(datetime, row.ts)
            trading_date = ts.date()
            close = float(cast(float, row.close))

            sma50 = (
                float(cast(float, row.sma50))
                if pd.notna(row.sma50)
                else None
            )
            realized_volatility = (
                float(cast(float, row.realized_volatility))
                if pd.notna(row.realized_volatility)
                else None
            )
            rv_percentile = (
                float(cast(float, row.rv_percentile))
                if pd.notna(row.rv_percentile)
                else None
            )

            iv_rank = iv_percentiles.get(trading_date)
            atr14 = atr_by_date.get(trading_date)

            classification = classify_regime(
                close=close,
                sma50=sma50,
                atr14=atr14,
                realized_volatility=realized_volatility,
                rv_percentile=rv_percentile,
                iv_rank=iv_rank,
                iv_percentile=iv_rank,
            )

            store.write_market_regime(
                symbol=args.symbol,
                ts=ts,
                trend_regime=classification.trend_regime,
                volatility_regime=classification.volatility_regime,
                iv_regime=classification.iv_regime,
                regime=classification.regime,
                features=classification.features,
            )

            written += 1

        print(f"{args.symbol}: regimes_written={written}")
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())