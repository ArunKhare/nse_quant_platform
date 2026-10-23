"""Multi-timeframe feature engineering for NSE spot candles."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from nse_quant.persistence.duckdb_store import DuckDBStore


@dataclass(frozen=True)
class SpotFeatureBuilder:
    """Build lookahead-safe spot features from persisted candles."""

    store: DuckDBStore

    def build(
        self,
        symbol: str,
        from_ts: pd.Timestamp | None = None,
        to_ts: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        minute = self._read_candles(symbol, "1m", from_ts, to_ts)
        minute_15 = self._read_candles(symbol, "15m", from_ts, to_ts)
        minute_60 = self._read_candles(symbol, "60m", from_ts, to_ts)

        if minute.empty:
            return pd.DataFrame()

        features = self._build_minute_features(minute)
        features = self._join_higher_timeframe(
            features,
            minute_15,
            prefix="15m",
        )
        features = self._join_higher_timeframe(
            features,
            minute_60,
            prefix="60m",
        )

        return features

    def _read_candles(
        self,
        symbol: str,
        interval: str,
        from_ts: pd.Timestamp | None,
        to_ts: pd.Timestamp | None,
    ) -> pd.DataFrame:
        frame = self.store.read_spot_candles(
            symbol=symbol,
            interval=interval,
            from_ts=from_ts,
            to_ts=to_ts,
        )

        if frame.empty:
            return frame

        frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
        return frame.sort_values("ts").reset_index(drop=True)

    def _build_minute_features(self, candles: pd.DataFrame) -> pd.DataFrame:
        frame = candles.copy()

        frame["return_1m"] = np.log(frame["close"] / frame["close"].shift(1))

        frame["rv_1m_30"] = frame["return_1m"].rolling(window=30, min_periods=30).std() * np.sqrt(
            252 * 375
        )

        frame["atr_1m_14"] = self._atr(frame, window=14)

        typical_price = (frame["high"] + frame["low"] + frame["close"]) / 3

        frame["vwap_1m"] = (typical_price * frame["volume"]).cumsum() / frame["volume"].replace(
            0, np.nan
        ).cumsum()

        frame["vwap_distance_1m"] = frame["close"] / frame["vwap_1m"] - 1

        volume_mean = frame["volume"].rolling(window=30, min_periods=30).mean()
        volume_std = frame["volume"].rolling(window=30, min_periods=30).std()

        frame["volume_zscore_1m_30"] = (frame["volume"] - volume_mean) / volume_std.replace(
            0, np.nan
        )

        return frame[
            [
                "symbol",
                "ts",
                "close",
                "return_1m",
                "rv_1m_30",
                "atr_1m_14",
                "vwap_1m",
                "vwap_distance_1m",
                "volume_zscore_1m_30",
            ]
        ]

    def _join_higher_timeframe(
        self,
        features: pd.DataFrame,
        candles: pd.DataFrame,
        prefix: str,
    ) -> pd.DataFrame:
        if candles.empty:
            features[f"trend_{prefix}"] = np.nan
            features[f"atr_{prefix}_14"] = np.nan
            features[f"range_position_{prefix}"] = np.nan
            return features

        higher = candles.copy()
        higher["trend"] = higher["close"] / higher["close"].shift(1) - 1
        higher["atr"] = self._atr(higher, window=14)
        higher["range_position"] = (higher["close"] - higher["low"]) / (
            higher["high"] - higher["low"]
        ).replace(0, np.nan)

        # A higher-timeframe bar is usable only after it closes.
        higher["available_ts"] = higher["ts"] + pd.to_timedelta(
            {"15m": "15min", "60m": "60min"}[prefix]
        )

        higher_features = higher[
            [
                "available_ts",
                "trend",
                "atr",
                "range_position",
            ]
        ].sort_values("available_ts")

        features = pd.merge_asof(
            features.sort_values("ts"),
            higher_features.rename(
                columns={
                    "trend": f"trend_{prefix}",
                    "atr": f"atr_{prefix}_14",
                    "range_position": f"range_position_{prefix}",
                }
            ),
            left_on="ts",
            right_on="available_ts",
            direction="backward",
        )

        return features.drop(columns=["available_ts"])

    @staticmethod
    def _atr(frame: pd.DataFrame, window: int) -> pd.Series:
        previous_close = frame["close"].shift(1)

        true_range = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - previous_close).abs(),
                (frame["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        return true_range.rolling(window=window, min_periods=window).mean()
