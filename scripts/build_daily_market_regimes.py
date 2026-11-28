"""Build point-in-time market regimes from persisted daily  data.

 -> combined trend / volatility / IV / market regime

This script reads daily spot candles, option IV history, and spot ATR features
from the legacy DuckDB store, calculates trend, volatility, and implied
volatility regime features, classifies each trading day into a market regime,
and writes the result to the ``market_regimes`` table.

It is a **legacy regime builder only**. It does not read or write Medallion
Bronze, Silver, or Gold data, does not use the Parquet warehouse, and does not
assert decision eligibility, publication status, or trading authority.

Data flow
---------

.. code-block:: text

    spot_candles (interval = 'day')
        -> daily close
        -> SMA(50)
        -> daily returns
        -> 20-day annualized realized volatility
        -> 252-day rolling realized-volatility percentile

    option_stream
    underlying_iv_observations
        -> daily average option IV
        -> 252-day rolling IV rank

    spot_features
        -> latest available 1-minute ATR(14) per trading date

    classify_regime()
        -> market_regimes

Required inputs
---------------

The script requires daily candles in the legacy ``spot_candles`` table:

.. code-block:: sql

    SELECT ts, close
    FROM spot_candles
    WHERE symbol = ?
      AND interval = 'day'

If no daily candles are available for the requested symbol and date range, the
script prints a message and exits without writing any regimes.

It also reads:

- ``option_stream.iv`` for historical option IV observations.
- ``underlying_iv_observations.iv`` for separately stored underlying IV
  observations.
- ``spot_features.atr_1m_14`` for the ATR input.

Features calculated
-------------------

Trend features
~~~~~~~~~~~~~~

- ``sma50``: Fifty-trading-day simple moving average of the daily close.

  .. math::

      sma50_t =
      \frac{1}{50}\sum_{i=t-49}^{t} close_i

- ``returns``: One-day percentage return of the daily close.

  .. math::

      return_t =
      \frac{close_t}{close_{t-1}} - 1

Volatility features
~~~~~~~~~~~~~~~~~~~

- ``realized_volatility``: Annualized realized volatility calculated from the
  standard deviation of the previous 20 daily returns. The script uses sample
  standard deviation with ``ddof=1`` and annualizes using 252 trading days.

  .. math::

      realized\_volatility_t =
      std(return_{t-19:t}, ddof=1) \times \sqrt{252}

- ``rv_percentile``: Rolling percentile of current realized volatility within
  the previous 252 daily realized-volatility observations.

Implied-volatility features
~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``atm_iv``: Daily average of all non-null option IV values from
  ``option_stream`` and ``underlying_iv_observations`` for the underlying.

  .. important::
      Despite the SQL alias ``atm_iv``, the current implementation averages
      all available non-null option IV values. It is **not** an ATM-only IV
      calculation.

- ``iv_rank``: Rolling 252-day percentile rank of the current daily average IV
  relative to prior daily average IV values.

  .. math::

      iv\_rank_t =
      100 \times
      \frac{\#\{iv_i < iv_t : i \in [t-251,t-1]\}}
           {251}

  The implementation requires at least 30 observations before producing an IV
  rank.

ATR feature
~~~~~~~~~~~

- ``atr14``:  "14-day average true range from daily OHLC candles".

Regimes classified
------------------

For each eligible daily candle, the script calls ``classify_regime()`` with:

- Daily close.
- SMA(50).
- Latest available 1-minute ATR(14).
- 20-day annualized realized volatility.
- 252-day realized-volatility percentile.
- Daily IV rank, used as both IV rank and IV percentile.

The classifier produces:

- ``trend_regime``
- ``volatility_regime``
- ``iv_regime``
- ``regime``
- ``features``

The exact labels and thresholds are determined by
``nse_quant.research.regimes.classify_regime``.

Output storage
--------------

The script writes one regime row per symbol and daily timestamp into:

.. code-block:: sql

    market_regimes

The persisted columns are:

.. code-block:: text

    symbol
    ts
    trend_regime
    volatility_regime
    iv_regime
    regime
    features

The primary key is:

.. code-block:: text

    (symbol, ts)

The ``features`` column stores the classifier feature payload as JSON.

Warm-up behavior
----------------

The current implementation filters daily candles using the requested
``--from`` date. Therefore, rolling indicators have insufficient history at the
beginning of the requested range:

- SMA(50) requires 50 daily closes.
- Realized volatility requires 20 daily returns, or 21 daily closes.
- Realized-volatility percentile uses a 252-day rolling window.
- IV rank requires at least 30 daily IV observations and uses a 252-day
  rolling window.

Affected values remain ``NULL``. The script does not fill, interpolate,
backfill, or synthesize missing history.

Current limitations
-------------------

- The daily SMA, realized volatility, and RV percentile are calculated only
  from candles within the requested date range, so their values depend on the
  selected ``--from`` date.
- IV history is read using all available observations up to ``--to``, rather
  than being restricted to the requested start date.
- The IV feature is a daily average of all available option IVs, not an
  ATM-specific IV.
- ATR is sourced from the latest 1-minute ATR(14), not from daily OHLC bars.
- The script writes directly to legacy ``market_regimes`` without a versioned
  build ID, immutable input snapshot, validation manifest, or audited
  publication record.
- It does not consume Medallion Bronze, Silver, or Gold revisions.

Command-line interface
----------------------

.. code-block:: powershell

    uv run python scripts/build_daily_market_regimes.py `
      --symbol NIFTY `
      --from 2023-11-19 `
      --to 2026-11-28

Arguments:

- ``--symbol``: Underlying symbol, for example ``NIFTY``.
- ``--from``: Inclusive start date in ISO format, for example ``2026-10-28``.
- ``--to``: Inclusive end date in ISO format, for example ``2026-10-30``.

Examples
--------

Build regimes for NIFTY over three trading days:

.. code-block:: powershell

    uv run python scripts/build_market_regimes.py `
      --symbol NIFTY `
      --from 2026-10-28 `
      --to 2026-10-30

Build regimes for a longer historical range:

.. code-block:: powershell

    uv run python scripts/build_market_regimes.py `
      --symbol NIFTY `
      --from 2026-08-01 `
      --to 2026-11-18

Safety and scope
----------------

- Reads only persisted legacy DuckDB data.
- Writes only to the legacy ``market_regimes`` table.
- Does not acquire live market data.
- Does not modify ``option_stream``.
- Does not modify ``spot_candles`` or ``spot_features``.
- Does not write Medallion Bronze, Silver, or Gold data.
- Does not fill missing candles, IV observations, or regime inputs.
- Does not assert decision eligibility, publication, or trading authority.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Any, cast

import pandas as pd

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.regimes import (
    classify_regime,
    rolling_percentile,
)

SCRIPT_VERSION = "market-regime-builder@2"
RV_WINDOW = 20
RV_PERCENTILE_WINDOW = 252
SMA_WINDOW = 50
IV_RANK_WINDOW = 252
IV_RANK_MIN_PERIODS = 30
WARMUP_TRADING_DAYS = RV_PERCENTILE_WINDOW + 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build historical market regimes")

    parser.add_argument("--symbol", required=True)
    parser.add_argument("--from", dest="from_ts", required=True)
    parser.add_argument("--to", dest="to_ts", required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and report regimes without writing to market_regimes.",
    )
    parser.add_argument(
        "--warmup-trading-days",
        type=int,
        default=WARMUP_TRADING_DAYS,
        help="Calendar-day buffer added before --from for indicator warm-up.",
    )

    return parser.parse_args()


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _load_daily_candles(
    store: DuckDBStore,
    *,
    symbol: str,
    warmup_start: date,
    end_date: date,
) -> pd.DataFrame:
    daily = store.conn.execute(
        """
        SELECT
            ts,
            open,
            high,
            low,
            close
        FROM spot_candles
        WHERE symbol = ?
          AND interval = 'day'
          AND CAST(ts AS DATE) >= ?
          AND CAST(ts AS DATE) <= ?
        ORDER BY ts
        """,
        [symbol, warmup_start, end_date],
    ).fetchdf()

    if daily.empty:
        return daily

    daily["ts"] = pd.to_datetime(daily["ts"], utc=True)
    daily["trading_date"] = daily["ts"].dt.tz_convert("Asia/Kolkata").dt.date
    daily = daily.drop_duplicates(subset=["trading_date"], keep="last")
    daily = daily.sort_values("trading_date").reset_index(drop=True)

    daily["sma50"] = daily["close"].rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()
    daily["returns"] = daily["close"].pct_change()
    daily["previous_close"] = daily["close"].shift(1)

    daily["true_range"] = pd.concat(
        [
            daily["high"] - daily["low"],
            (daily["high"] - daily["previous_close"]).abs(),
            (daily["low"] - daily["previous_close"]).abs(),
        ],
        axis=1,
    ).max(axis=1)

    daily["atr14"] = (
        daily["true_range"]
        .rolling(
            window=14,
            min_periods=14,
        )
        .mean()
    )
    daily["realized_volatility"] = daily["returns"].rolling(RV_WINDOW, min_periods=RV_WINDOW).std(ddof=1) * (252**0.5)
    daily["rv_percentile"] = rolling_percentile(
        daily["realized_volatility"],
        window=RV_PERCENTILE_WINDOW,
    )

    return daily


def _load_iv_history(
    store: DuckDBStore,
    *,
    symbol: str,
    end_date: date,
) -> pd.DataFrame:
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
        [symbol, end_date, symbol, end_date],
    ).fetchdf()

    if iv_history.empty:
        return iv_history

    iv_history["trading_date"] = pd.to_datetime(iv_history["trading_date"]).dt.date
    iv_history["iv_rank"] = (
        iv_history["atm_iv"]
        .rolling(IV_RANK_WINDOW, min_periods=IV_RANK_MIN_PERIODS)
        .apply(
            lambda values: (values[-1] > values[:-1]).mean() * 100 if len(values) > 1 else float("nan"),
            raw=True,
        )
    )

    return iv_history


def main() -> int:
    args = parse_args()

    requested_start = _parse_date(args.from_ts)
    end_date = _parse_date(args.to_ts)

    if requested_start > end_date:
        raise ValueError("--from must be <= --to")

    warmup_start = requested_start - timedelta(days=args.warmup_trading_days)

    store = DuckDBStore()

    try:
        daily = _load_daily_candles(
            store,
            symbol=args.symbol,
            warmup_start=warmup_start,
            end_date=end_date,
        )

        if daily.empty:
            print(f"No daily candles for {args.symbol}")
            return 0

        iv_history = _load_iv_history(
            store,
            symbol=args.symbol,
            end_date=end_date,
        )

        iv_percentiles: dict[date, float] = {}

        if not iv_history.empty:
            print(f"IV history days={len(iv_history)}, last_date={iv_history['trading_date'].iloc[-1]}")

            iv_percentiles = {
                cast(date, row.trading_date): float(cast(float, row.iv_rank))
                for row in iv_history.itertuples()
                if pd.notna(row.iv_rank)
            }

            print(
                "IV rank available dates:",
                len(iv_percentiles),
                "last:",
                max(iv_percentiles) if iv_percentiles else None,
            )

        target_daily = daily[(daily["trading_date"] >= requested_start) & (daily["trading_date"] <= end_date)]

        if target_daily.empty:
            print(f"No daily candles in requested range for {args.symbol}: {requested_start} to {end_date}")
            return 0

        written = 0
        skipped = 0

        for row in target_daily.itertuples():
            trading_date = cast(date, row.trading_date)
            close = float(cast(float, row.close))

            sma50 = float(cast(float, row.sma50)) if pd.notna(row.sma50) else None

            realized_volatility = (
                float(cast(float, row.realized_volatility)) if pd.notna(row.realized_volatility) else None
            )

            rv_percentile = float(cast(float, row.rv_percentile)) if pd.notna(row.rv_percentile) else None

            iv_rank = iv_percentiles.get(trading_date)

            atr14 = float(cast(float, row.atr14)) if pd.notna(row.atr14) else None

            if sma50 is None or realized_volatility is None:
                skipped += 1
                continue

            classification = classify_regime(
                close=close,
                sma=sma50,
                atr=atr14,
                realized_volatility=realized_volatility,
                rv_percentile=rv_percentile,
                iv_rank=iv_rank,
                iv_percentile=iv_rank,
            )

            features: dict[str, Any] = dict(classification.features)
            features["build_contract"] = {
                "script_version": SCRIPT_VERSION,
                "requested_start": requested_start.isoformat(),
                "requested_end": end_date.isoformat(),
                "warmup_start": warmup_start.isoformat(),
                "warmup_trading_days": args.warmup_trading_days,
                "sma_window": SMA_WINDOW,
                "rv_window": RV_WINDOW,
                "rv_percentile_window": RV_PERCENTILE_WINDOW,
                "iv_rank_window": IV_RANK_WINDOW,
                "iv_rank_min_periods": IV_RANK_MIN_PERIODS,
                "atr_source": "spot_candles interval='day'",
                "atr_definition": "14-day average true range from daily OHLC candles",
                "dry_run": args.dry_run,
            }

            if args.dry_run:
                print(
                    json.dumps(
                        {
                            "symbol": args.symbol,
                            "trading_date": trading_date.isoformat(),
                            "regime": classification.regime,
                            "trend_regime": classification.trend_regime,
                            "volatility_regime": classification.volatility_regime,
                            "iv_regime": classification.iv_regime,
                            "features": features,
                        },
                        default=str,
                        indent=2,
                    )
                )
            else:
                store.write_market_regime(
                    symbol=args.symbol,
                    ts=cast(datetime, row.ts),
                    trend_regime=classification.trend_regime,
                    volatility_regime=classification.volatility_regime,
                    iv_regime=classification.iv_regime,
                    regime=classification.regime,
                    features=features,
                )

            written += 1

        print(
            f"{args.symbol}: "
            f"regimes_computed={written} "
            f"regimes_written={0 if args.dry_run else written} "
            f"insufficient_warmup_skipped={skipped} "
            f"dry_run={args.dry_run}"
        )
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
