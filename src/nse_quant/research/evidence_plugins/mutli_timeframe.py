"""Multi-timeframe evidence derived from completed 1-minute candles."""

from __future__ import annotations

from typing import Any

from nse_quant.research.candle_resampler import (
    latest_completed_candles,
)
from nse_quant.research.evidence_plugins.base import (
    DecisionContext,
)


class MultiTimeframeEvidencePlugin:
    name = "multi_timeframe"

    def __init__(
        self,
        store: Any,
        *,
        timeframes: tuple[str, ...] = ("1m", "15m", "60m"),
        lookback_candles: int = 60,
    ) -> None:
        self.store = store
        self.timeframes = timeframes
        self.lookback_candles = lookback_candles

    def build(self, context: DecisionContext) -> dict[str, Any]:
        one_minute_candles = self.store.latest_spot_candles(
            symbol=context.symbol,
            instrument_token=context.spot_instrument_token,
            interval="1m",
            limit=600,
        )

        timeframe_evidence = {
            "1m": self._build_from_candles(
                candles=one_minute_candles,
                interval_minutes=1,
            ),
        }

        interval_minutes = {
            "15m": 15,
            "60m": 60,
        }

        for timeframe in self.timeframes:
            if timeframe == "1m":
                continue

            minutes = interval_minutes.get(timeframe)

            if minutes is None:
                timeframe_evidence[timeframe] = {
                    "available": False,
                    "reason": "unsupported_timeframe",
                }
                continue

            timeframe_evidence[timeframe] = self._build_from_candles(
                candles=one_minute_candles,
                interval_minutes=minutes,
            )

        return {
            "available": any(
                item.get("available")
                for item in timeframe_evidence.values()
            ),
            "timeframes": timeframe_evidence,
        }

    def _build_from_candles(
        self,
        *,
        candles: list[dict[str, Any]],
        interval_minutes: int,
    ) -> dict[str, Any]:
        completed = latest_completed_candles(
            candles,
            interval_minutes=interval_minutes,
            limit=self.lookback_candles,
        )

        if len(completed) < 2:
            return {
                "available": False,
                "reason": "insufficient_completed_candles",
                "completed_candles": len(completed),
            }

        closes = [candle.close for candle in completed]

        recent_return = (
            closes[-1] / closes[-21] - 1
            if len(closes) >= 21
            else None
        )

        recent_high = (
            max(closes[-20:])
            if len(closes) >= 20
            else None
        )

        recent_low = (
            min(closes[-20:])
            if len(closes) >= 20
            else None
        )

        range_position = (
            (closes[-1] - recent_low) / (recent_high - recent_low)
            if recent_high is not None
            and recent_low is not None
            and recent_high > recent_low
            else None
        )

        returns = [
            closes[i] / closes[i - 1] - 1
            for i in range(1, len(closes))
        ]

        realized_volatility = (
            (sum(value * value for value in returns[-20:]) / 20) ** 0.5
            if len(returns) >= 20
            else None
        )

        return {
            "available": True,
            "close": closes[-1],
            "recent_return_20": recent_return,
            "recent_high_20": recent_high,
            "recent_low_20": recent_low,
            "range_position_20": range_position,
            "realized_volatility_20": realized_volatility,
            "completed_candles": len(completed),
        }