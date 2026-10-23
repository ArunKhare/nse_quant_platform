"""Multi-timeframe trend evidence plugin."""

from __future__ import annotations

from typing import Any

from nse_quant.research.candle_resampler import ResampledCandle, latest_completed_candles
from nse_quant.research.evidence_plugins.base import (
    DecisionContext,
    EvidencePlugin,
)

TIMEFRAME_RULES: dict[str, tuple[int, int]] = {
    "1m": (1, 60),
    "15m": (15, 16),
    "60m": (60, 61),
}


class MultiTimeframeTrendPlugin(EvidencePlugin):
    name = "multi_timeframe_trend"

    def __init__(
        self,
        *,
        store: Any,
        timeframes: list[str],
        history_limit: int = 6000,
    ) -> None:
        unknown = set(timeframes) - set(TIMEFRAME_RULES)

        if unknown:
            raise ValueError(
                f"Unsupported timeframes: {sorted(unknown)}. Supported: {sorted(TIMEFRAME_RULES)}"
            )

        if not timeframes:
            raise ValueError("At least one timeframe must be configured")

        self._store = store
        self._timeframes = timeframes
        self._history_limit = history_limit

    def build(self, context: DecisionContext) -> dict[str, Any]:
        as_of = context.ts
        token = context.spot_instrument_token

        rows = self._store.conn.execute(
            """
            SELECT
                ts,
                open,
                high,
                low,
                close,
                volume
            FROM spot_candles
            WHERE instrument_token = ?
              AND interval = '1m'
              AND ts <= ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            [token, as_of, self._history_limit],
        ).fetchall()

        candles = [
            {
                "date": row[0],
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5],
            }
            for row in rows
        ]

        if not candles:
            return {
                "available": True,
                "complete": False,
                "reason": "no_1m_history",
                "timeframes": {},
            }

        timeframe_results: dict[str, Any] = {}

        for timeframe in self._timeframes:
            interval_minutes, required_buckets = TIMEFRAME_RULES[timeframe]

            completed = latest_completed_candles(
                candles,
                interval_minutes=interval_minutes,
                limit=required_buckets,
            )

            trend = self._trend(completed) if len(completed) >= required_buckets else None

            timeframe_results[timeframe] = {
                "trend": trend,
                "completed_buckets": len(completed),
                "required_buckets": required_buckets,
                "complete": trend is not None,
            }

        available_trends = [
            result["trend"] for result in timeframe_results.values() if result["trend"] is not None
        ]

        complete = len(available_trends) == len(self._timeframes)

        return {
            "available": True,
            "complete": complete,
            "as_of": as_of.isoformat(),
            "bars_used": len(candles),
            "timeframes": timeframe_results,
            "alignment": (self._alignment(available_trends) if complete else None),
        }

    def _trend(
        self,
        candles: list[ResampledCandle],
    ) -> str:
        first_close = candles[0].close
        last_close = candles[-1].close
        change = last_close - first_close

        if change > 0:
            return "UP"

        if change < 0:
            return "DOWN"

        return "FLAT"

    def _alignment(
        self,
        trends: list[str],
    ) -> str:
        if all(trend == "UP" for trend in trends):
            return "BULLISH"

        if all(trend == "DOWN" for trend in trends):
            return "BEARISH"

        return "MIXED"
