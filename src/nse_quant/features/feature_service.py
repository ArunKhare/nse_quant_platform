"""Access latest complete spot features for decision-making."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import pandas as pd

if TYPE_CHECKING:
    from nse_quant.persistence.duckdb_store import DuckDBStore


@dataclass(frozen=True)
class SpotFeatureSnapshot:
    symbol: str
    ts: pd.Timestamp
    close: float
    return_1m: float | None
    rv_1m_30: float | None
    atr_1m_14: float | None
    vwap_distance_1m: float | None
    volume_zscore_1m_30: float | None
    trend_15m: float | None
    atr_15m_14: float | None
    range_position_15m: float | None
    trend_60m: float | None
    atr_60m_14: float | None
    range_position_60m: float | None


class SpotFeatureService:
    def __init__(
        self,
        store: DuckDBStore,
        max_age_seconds: int = 300,
    ) -> None:
        self._store = store
        self._max_age_seconds = max_age_seconds

    def latest(self, symbol: str) -> SpotFeatureSnapshot | None:
        row = self._store.conn.execute(
            """
            SELECT *
            FROM spot_features
            WHERE symbol = ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            [symbol],
        ).fetchdf()

        if row.empty:
            return None

        record = row.iloc[0]
        return SpotFeatureSnapshot(
            symbol=str(record["symbol"]),
            ts=pd.Timestamp(record["ts"]),
            close=float(record["close"]),
            return_1m=self._optional_float(record["return_1m"]),
            rv_1m_30=self._optional_float(record["rv_1m_30"]),
            atr_1m_14=self._optional_float(record["atr_1m_14"]),
            vwap_distance_1m=self._optional_float(record["vwap_distance_1m"]),
            volume_zscore_1m_30=self._optional_float(record["volume_zscore_1m_30"]),
            trend_15m=self._optional_float(record["trend_15m"]),
            atr_15m_14=self._optional_float(record["atr_15m_14"]),
            range_position_15m=self._optional_float(record["range_position_15m"]),
            trend_60m=self._optional_float(record["trend_60m"]),
            atr_60m_14=self._optional_float(record["atr_60m_14"]),
            range_position_60m=self._optional_float(record["range_position_60m"]),
        )

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if value is None or pd.isna(value):
            return None
        return float(cast(float, value))
