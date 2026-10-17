"""Derived daily aggregates from intraday feature snapshots."""

from __future__ import annotations

from typing import Any

import pandas as pd


class FeatureCompactor:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def daily_frame(self, underlying: str, trade_date: str) -> pd.DataFrame:
        return self.conn.execute(
            """
            SELECT
                CAST(ts AS DATE) AS trade_date,
                MIN(ts) AS first_snapshot,
                MAX(ts) AS last_snapshot,
                AVG(spot) AS avg_spot,
                MAX(spot) AS high_spot,
                MIN(spot) AS low_spot,
                AVG(atm_iv) AS avg_atm_iv,
                MAX(atm_iv) AS max_atm_iv,
                MIN(atm_iv) AS min_atm_iv,
                AVG(iv_rank) AS avg_iv_rank,
                AVG(realized_vol) AS avg_realized_vol,
                AVG(pcr) AS avg_pcr,
                MAX(expected_move_points) AS max_expected_move_points,
                COUNT(*) AS snapshot_count
            FROM feature_snapshots
            WHERE underlying = ?
              AND CAST(ts AS DATE) = ?
            GROUP BY CAST(ts AS DATE)
            """,
            [underlying, trade_date],
        ).df()

    def compact(self, underlying: str, trade_date: str) -> dict[str, Any]:
        frame = self.daily_frame(underlying, trade_date)

        if frame.empty:
            return {}

        record = frame.iloc[0].to_dict()
        return {key: (None if pd.isna(value) else value) for key, value in record.items()}