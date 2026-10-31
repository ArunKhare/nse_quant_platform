"""Look-ahead-safe volume-flow evidence from completed candles."""

from __future__ import annotations

from typing import Any

from nse_quant.research.candle_resampler import (
    latest_completed_candles,
)
from nse_quant.research.evidence_plugins.base import (
    DecisionContext,
    EvidencePlugin,
)


class VolumeFlowPlugin(EvidencePlugin):
    name = "volume_flow"

    def __init__(
        self,
        *,
        store: Any,
        settings: Any,
    ) -> None:
        self._store = store
        self._settings = settings

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
            [
                token,
                as_of,
                self._settings.history_limit,
            ],
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
                "as_of": as_of.isoformat(),
                "bars_used": 0,
                "timeframes": {},
                "reason": "no_1m_history",
            }

        candles.sort(key=lambda candle: candle["date"])

        timeframe_results: dict[str, Any] = {}

        for timeframe in self._settings.timeframes:
            interval_minutes = self._interval_minutes(timeframe)
            required_bars = self._settings.baseline_periods + 1

            completed = latest_completed_candles(
                candles,
                interval_minutes=interval_minutes,
                limit=required_bars,
            )

            volumes = [candle.volume for candle in completed]

            if not volumes:
                latest_volume = None
                baseline: list[float] = []
            else:
                latest_volume = volumes[-1]
                baseline = volumes[:-1]

            average_volume = sum(baseline) / len(baseline) if baseline else None

            rvol = self._relative_volume(
                latest_volume,
                average_volume,
            )
            zscore = self._volume_zscore(
                latest_volume,
                baseline,
            )

            timeframe_results[timeframe] = {
                "latest_volume": latest_volume,
                "average_volume": average_volume,
                "rvol": rvol,
                "volume_zscore": zscore,
                "volume_trend": self._volume_trend(rvol),
                "complete": rvol is not None,
                "required_bars": required_bars,
                "available_bars": len(completed),
            }

        complete = any(result["complete"] for result in timeframe_results.values())

        return {
            "available": True,
            "complete": complete,
            "as_of": as_of.isoformat(),
            "bars_used": len(candles),
            "timeframes": timeframe_results,
            "reason": None if complete else "insufficient_completed_history",
        }

    @staticmethod
    def _interval_minutes(timeframe: str) -> int:
        rules = {
            "1m": 1,
            "15m": 15,
            "60m": 60,
        }

        if timeframe not in rules:
            raise ValueError(f"Unsupported timeframe: {timeframe!r}. Supported: {sorted(rules)}")

        return rules[timeframe]

    @staticmethod
    def _relative_volume(
        latest_volume: float | None,
        average_volume: float | None,
    ) -> float | None:
        if latest_volume is None or average_volume is None:
            return None

        if average_volume <= 0:
            return None

        return latest_volume / average_volume

    @staticmethod
    def _volume_zscore(
        latest_volume: float | None,
        baseline: list[float],
    ) -> float | None:
        if latest_volume is None or len(baseline) < 2:
            return None

        mean = sum(baseline) / len(baseline)
        variance = sum((value - mean) ** 2 for value in baseline) / len(baseline)
        std_dev = variance**0.5

        if std_dev == 0:
            return None

        return (latest_volume - mean) / std_dev

    @staticmethod
    def _volume_trend(rvol: float | None) -> str | None:
        if rvol is None:
            return None

        if rvol > 1.0:
            return "RISING"

        if rvol < 1.0:
            return "FALLING"

        return "FLAT"
