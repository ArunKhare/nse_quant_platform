"""Build multi-timeframe spot features from persisted candles.

This script reads persisted NIFTY spot candles from the legacy DuckDB store,
computes minute-level technical features, and persists the resulting feature
rows into the ``spot_features`` table.

It is a **legacy spot-candle feature builder only**. It does not read or calculate
option-chain data, implied volatility, option Greeks, PCR, open interest,
regime classifications, or strategy eligibility.

Data flow
---------

.. code-block:: text

    spot_candles (1m)
    spot_candles (15m)
    spot_candles (60m)
            |
            v
    SpotFeatureBuilder
            |
            v
    spot_features

Required inputs
---------------

The builder requires 1-minute candles. If no 1-minute candles are available
for the requested symbol and time range, no features are built or written.

It also reads persisted 15-minute and 60-minute candles to enrich each 1-minute
observation with higher-timeframe context. If either higher-timeframe series
is unavailable, the corresponding higher-timeframe feature columns are set to
``NULL`` rather than causing the entire build to fail.

Features calculated
-------------------

The following features are calculated for every 1-minute candle:

- ``return_1m``: One-minute logarithmic price return.

  .. math::

      return\_1m_t = \ln\left(\frac{close_t}{close_{t-1}}\right)

- ``rv_1m_30``: Annualized realized volatility over the previous 30 one-minute
  returns. It uses the sample standard deviation with ``ddof=1`` and annualizes
  using 252 trading days and 375 minutes per trading day.

  .. math::

      rv\_1m\_30_t =
      std(return\_1m_{t-29:t}) \times \sqrt{252 \times 375}

- ``atr_1m_14``: Fourteen-period average true range calculated from the
  current high, low, and previous close.

  .. math::

      TR_t = \max\left(
          high_t - low_t,
          |high_t - close_{t-1}|,
          |low_t - close_{t-1}|
      \right)

  .. math::

      atr\_1m\_14_t =
      \frac{1}{14}\sum_{i=t-13}^{t} TR_i

- ``vwap_1m``: Cumulative volume-weighted average price using the typical
  price.

  .. math::

      typical\_price_t =
      \frac{high_t + low_t + close_t}{3}

  .. math::

      vwap\_1m_t =
      \frac{\sum_{i \le t} typical\_price_i \times volume_i}
           {\sum_{i \le t} volume_i}

- ``vwap_distance_1m``: Relative distance of the current close from the
  cumulative VWAP.

  .. math::

      vwap\_distance\_1m_t =
      \frac{close_t}{vwap\_1m_t} - 1

- ``volume_zscore_1m_30``: Standardized current volume relative to the
  previous 30 one-minute bars.

  .. math::

      volume\_zscore\_1m\_30_t =
      \frac{volume_t - mean(volume_{t-29:t})}
           {std(volume_{t-29:t})}

Higher-timeframe features
-------------------------

For each 1-minute observation, the builder joins the most recently **closed**
15-minute and 60-minute candle. A higher-timeframe candle is not used until its
interval has elapsed, preventing lookahead leakage.

For each higher timeframe, the script calculates:

- ``trend_{interval}``: Simple bar return.

  .. math::

      trend\_interval_t =
      \frac{close_t}{close_{t-1}} - 1

- ``atr_{interval}_14``: Fourteen-period average true range on that timeframe.

- ``range_position_{interval}``: Relative position of the close within the
  bar's high-low range.

  .. math::

      range\_position\_interval_t =
      \frac{close_t - low_t}{high_t - low_t}

The resulting columns are:

- ``trend_15m``
- ``atr_15m_14``
- ``range_position_15m``
- ``trend_60m``
- ``atr_60m_14``
- ``range_position_60m``

Output storage
--------------

The script writes one row per symbol and 1-minute timestamp into:

.. code-block:: sql

    spot_features

The persisted columns are:

.. code-block:: text

    symbol
    ts
    close
    return_1m
    rv_1m_30
    atr_1m_14
    vwap_1m
    vwap_distance_1m
    volume_zscore_1m_30
    trend_15m
    atr_15m_14
    range_position_15m
    trend_60m
    atr_60m_14
    range_position_60m

The primary key is:

.. code-block:: text

    (symbol, ts)

Warm-up behavior
----------------

Rolling indicators require enough prior candles before producing a non-null
value:

- ``rv_1m_30`` requires 30 prior 1-minute returns.
- ``atr_1m_14`` requires 14 prior 1-minute bars.
- ``volume_zscore_1m_30`` requires 30 prior 1-minute bars.
- ``atr_15m_14`` requires 14 prior 15-minute bars.
- ``atr_60m_14`` requires 14 prior 60-minute bars.

During the warm-up period, affected values remain ``NULL``. The script does not
fill, interpolate, or synthesize missing indicator values.

Time handling
-------------

If ``--from`` or ``--to`` is supplied as a date-only value, the script treats:

- ``--from`` as midnight Asia/Kolkata on that date.
- ``--to`` as 23:59:59 Asia/Kolkata on that date.

This makes an inclusive date-range invocation intuitive:

.. code-block:: powershell

    uv run python scripts/build_spot_features.py `
      --symbol NIFTY `
      --from 2026-11-18 `
      --to 2026-11-28

Command-line interface
----------------------

.. code-block:: powershell

    uv run python scripts/build_spot_features.py

Build features for one or more symbols:

.. code-block:: powershell

    uv run python scripts/build_spot_features.py `
      --symbol NIFTY `
      --symbol BANKNIFTY

Build features for a date range:

.. code-block:: powershell

    uv run python scripts/build_spot_features.py `
      --symbol NIFTY `
      --from 2026-11-17 `
      --to 2026-11-18

Relationship to other scripts
-----------------------------

This script is a prerequisite for ``scripts/build_market_regimes.py`` only
through the ``atr_1m_14`` column. The regime builder reads the latest
available 1-minute ATR(14) for each trading date and uses it as its ATR input.

.. code-block:: text

    build_spot_features.py
      -> spot_features.atr_1m_14
      -> build_market_regimes.py
      -> market_regimes

It does not calculate daily IV, IV rank, realized volatility from daily bars,
SMA(50), PCR, straddle, expected move, or any option-chain feature.

Safety and scope
----------------

- Reads only persisted candles; it does not acquire live market data.
- Writes only to the legacy ``spot_features`` table.
- Does not modify ``option_stream``.
- Does not write Medallion Bronze, Silver, or Gold data.
- Does not assert decision eligibility, publication, or trading authority.
- Does not fill missing candles or interpolate missing features.

Examples
--------

Build features for the configured default symbol:

.. code-block:: powershell

    uv run python scripts/build_spot_features.py

Build features for NIFTY:

.. code-block:: powershell

    uv run python scripts/build_spot_features.py `
      --symbol NIFTY

Build features for NIFTY over a date range:

.. code-block:: powershell

    uv run python scripts/build_spot_features.py `
      --symbol NIFTY `
      --from 2026-11-17 `
      --to 2026-11-18

Build features for multiple symbols:

.. code-block:: powershell

    uv run python scripts/build_spot_features.py `
      --symbol NIFTY `
      --symbol BANKNIFTY
"""

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
