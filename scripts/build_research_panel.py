"""Build the daily Legacy research panel.
 builds a daily research panel by combining daily spot candles, daily aggregates of spot features,
 RV-regime results, and daily IV-surface metrics
Legacy 1m spot candles
  -> aggregate into daily OHLCV
  -> daily return and range percentage

Legacy spot_features
  -> daily mean/max aggregates

Legacy_run_warehouse_validate_research.py outputs
  -> RV regimes CSV
  -> daily IV surface CSV

Merge by trade_date
  -> daily_research_panel_NIFTY.csv
 Output: csv

Features in the panel:
    - Daily candle features
    - Daily spot-feature aggregates
    - RV regime fields
    - IV surface fields

    only merges the already-produced RV-regime and daily IV-surface CSVs into the panel.

pipeline order:
    1. Capture and store 1m/15m/60m candles
    2. build_spot_features.py
    3. Export option_stream to Parquet
    4. run_milestone2_research.py
        -> iv_surface_daily_NIFTY.csv
        -> rv_regimes_NIFTY.csv
    5. build_research_panel.py
        -> daily_research_panel_NIFTY.csv

"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument(
        "--rv-regimes",
        default=("data/research/milestone2/rv_regimes_NIFTY.csv"),
    )
    parser.add_argument("--iv-daily", default=("data/research/milestone2/iv_surface_daily_NIFTY.csv"))
    parser.add_argument(
        "--output",
        default=("data/research/milestone2/daily_research_panel_NIFTY.csv"),
    )
    return parser.parse_args()


def build_daily_candles(
    store: DuckDBStore,
    *,
    symbol: str,
) -> pd.DataFrame:
    frame = store.read_spot_candles(
        symbol=symbol,
        interval="1m",
    )

    if frame.empty:
        raise SystemExit(f"No 1m candles found for {symbol}")

    frame["ts"] = pd.to_datetime(frame["ts"])
    frame["trade_date"] = frame["ts"].dt.date

    daily = frame.groupby("trade_date", as_index=False).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        candle_count=("close", "count"),
    )

    daily["daily_return"] = daily["close"].pct_change()
    daily["range_pct"] = (daily["high"] - daily["low"]) / daily["close"].shift(1)

    daily["underlying"] = symbol

    return daily[
        [
            "trade_date",
            "underlying",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "candle_count",
            "daily_return",
            "range_pct",
        ]
    ]


def build_spot_feature_daily(
    store: DuckDBStore,
    *,
    symbol: str,
) -> pd.DataFrame:
    frame = store.conn.execute(
        """
        SELECT
            CAST(ts AS DATE) AS trade_date,
            symbol AS underlying,
            avg(close) AS mean_close,
            avg(return_1m) AS mean_return_1m,
            avg(rv_1m_30) AS mean_rv_1m_30,
            max(rv_1m_30) AS max_rv_1m_30,
            avg(atr_1m_14) AS mean_atr_1m_14,
            avg(vwap_distance_1m) AS mean_vwap_distance_1m,
            avg(volume_zscore_1m_30) AS mean_volume_zscore_1m_30,
            avg(trend_15m) AS mean_trend_15m,
            avg(atr_15m_14) AS mean_atr_15m_14,
            avg(range_position_15m) AS mean_range_position_15m,
            avg(trend_60m) AS mean_trend_60m,
            avg(atr_60m_14) AS mean_atr_60m_14,
            avg(range_position_60m) AS mean_range_position_60m
        FROM spot_features
        WHERE symbol = ?
        GROUP BY trade_date, underlying
        ORDER BY trade_date
        """,
        [symbol],
    ).fetchdf()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date

    return frame


def load_csv(
    path: str | Path,
) -> pd.DataFrame:
    path = Path(path)

    if not path.exists():
        return pd.DataFrame()

    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        print(f"Empty research file skipped: {path}")
        return pd.DataFrame()

    if "trade_date" in frame.columns:
        frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date

    return frame


def main() -> int:
    args = parse_args()

    store = DuckDBStore(read_only=True)

    candles = build_daily_candles(
        store,
        symbol=args.symbol,
    )

    spot_features = build_spot_feature_daily(
        store,
        symbol=args.symbol,
    )

    store.close()

    rv = load_csv(args.rv_regimes)
    iv = load_csv(args.iv_daily)

    candles["trade_date"] = pd.to_datetime(candles["trade_date"]).dt.date
    spot_features["trade_date"] = pd.to_datetime(spot_features["trade_date"]).dt.date

    panel = candles.merge(
        rv[
            [
                "trade_date",
                "realized_volatility",
                "rv_percentile",
                "rv_regime",
            ]
        ],
        on="trade_date",
        how="left",
    )

    panel = panel.merge(
        spot_features,
        on=["trade_date", "underlying"],
        how="left",
    )

    iv_columns = [
        "trade_date",
        "median_atm_iv_near",
        "median_atm_iv_next",
        "median_term_structure",
        "median_put_call_skew",
        "median_risk_reversal",
        "median_butterfly",
        "snapshots",
    ]

    available_iv_columns = [column for column in iv_columns if column in iv.columns]

    if available_iv_columns:
        panel = panel.merge(
            iv[available_iv_columns],
            on="trade_date",
            how="left",
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    panel.to_csv(output, index=False)

    print(f"Built {len(panel)} daily research rows for {args.symbol}")
    print(f"Saved: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
