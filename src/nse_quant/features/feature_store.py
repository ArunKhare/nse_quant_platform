"""Persistent intraday feature store."""

from __future__ import annotations

import json
from typing import Any

from nse_quant.core.models import MarketFeatures


class FeatureStore:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def save(self, run_id: str, features: MarketFeatures) -> str:
        feature_id = f"{features.underlying}:{features.expiry}:{features.ts.isoformat()}"
        columns = [
            "feature_id",
            "ts",
            "run_id",
            "underlying",
            "expiry",
            "spot",
            "atm_iv",
            "iv_rank",
            "iv_percentile",
            "realized_vol",
            "iv_rv_spread",
            "pcr",
            "total_call_oi",
            "total_put_oi",
            "max_pain",
            "liquidity_score",
        ]
        values: list[Any] = [
            feature_id,
            features.ts,
            run_id,
            features.underlying,
            features.expiry,
            features.spot,
            features.atm_iv,
            features.iv_rank,
            features.iv_percentile,
            features.realized_vol,
            features.iv_rv_spread,
            features.pcr,
            features.total_call_oi,
            features.total_put_oi,
            features.max_pain,
            features.liquidity_score,
        ]

        # Older retained feature_snapshots tables have the legacy "regime"
        # column but no "intraday_shape" column. Do not write intraday shape
        # into that legacy field: the two vocabularies are intentionally distinct.
        schema_columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info('feature_snapshots')").fetchall()
        }
        if "intraday_shape" in schema_columns:
            columns.append("intraday_shape")
            values.append(features.intraday_shape.value)

        columns.extend(
            [
                "short_momentum",
                "straddle_price",
                "expected_move_pct",
                "expected_move_points",
                "diagnostics",
            ]
        )
        values.extend(
            [
                features.short_momentum,
                features.straddle_price,
                features.expected_move_pct,
                features.expected_move_points,
                _json(features.diagnostics),
            ]
        )
        column_sql = ", ".join(f'"{column}"' for column in columns)
        placeholders = ", ".join("?" for _ in values)
        self.conn.execute(
            f"INSERT OR REPLACE INTO feature_snapshots ({column_sql}) VALUES ({placeholders})",
            values,
        )
        return feature_id

    def _intraday_shape_projection(self) -> str:
        schema_columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info('feature_snapshots')").fetchall()
        }
        if "intraday_shape" in schema_columns:
            return '"intraday_shape"'
        return "'UNKNOWN' AS intraday_shape"

    def latest(self, underlying: str) -> MarketFeatures | None:
        shape_projection = self._intraday_shape_projection()
        row = self.conn.execute(
            f"""
            SELECT feature_id, ts, run_id, underlying, expiry, spot, atm_iv,
                   iv_rank, iv_percentile, realized_vol, iv_rv_spread, pcr,
                   total_call_oi, total_put_oi, max_pain, liquidity_score,
                   {shape_projection}, short_momentum, straddle_price,
                   expected_move_pct, expected_move_points, diagnostics
            FROM feature_snapshots
            WHERE underlying = ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            [underlying],
        ).fetchone()

        return self._from_row(row) if row else None

    def history(
        self,
        underlying: str,
        start_ts: Any | None = None,
        end_ts: Any | None = None,
    ) -> list[MarketFeatures]:
        shape_projection = self._intraday_shape_projection()
        rows = self.conn.execute(
            f"""
            SELECT feature_id, ts, run_id, underlying, expiry, spot, atm_iv,
                   iv_rank, iv_percentile, realized_vol, iv_rv_spread, pcr,
                   total_call_oi, total_put_oi, max_pain, liquidity_score,
                   {shape_projection}, short_momentum, straddle_price,
                   expected_move_pct, expected_move_points, diagnostics
            FROM feature_snapshots
            WHERE underlying = ?
              AND (? IS NULL OR ts >= ?)
              AND (? IS NULL OR ts <= ?)
            ORDER BY ts
            """,
            [underlying, start_ts, start_ts, end_ts, end_ts],
        ).fetchall()

        return [self._from_row(row) for row in rows]

    def _from_row(self, row: tuple[Any, ...]) -> MarketFeatures:
        from nse_quant.core.models import IntradayShape

        return MarketFeatures(
            ts=row[1],
            underlying=row[3],
            spot=float(row[5]),
            expiry=row[4],
            atm_iv=row[6],
            iv_rank=row[7],
            iv_percentile=row[8],
            realized_vol=row[9],
            iv_rv_spread=row[10],
            pcr=row[11],
            total_call_oi=int(row[12]) if row[12] is not None else None,
            total_put_oi=int(row[13]) if row[13] is not None else None,
            max_pain=row[14],
            liquidity_score=row[15],
            intraday_shape=IntradayShape(row[16] or "UNKNOWN"),
            short_momentum=row[17],
            straddle_price=row[18],
            expected_move_pct=row[19],
            expected_move_points=row[20],
            diagnostics=json.loads(row[21]) if row[21] else {},
        )


def _json(value: Any) -> str:
    return json.dumps(value, default=str)
