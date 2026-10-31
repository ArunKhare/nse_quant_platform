"""Look-ahead-safe market-structure evidence from completed candles."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from nse_quant.research.candle_resampler import (
    latest_completed_candles,
)
from nse_quant.research.evidence_plugins.base import (
    DecisionContext,
    EvidencePlugin,
)


class MarketStructurePlugin(EvidencePlugin):
    name = "market_structure"

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
            required_bars = (self._settings.swing_lookback * 2) + 1

            completed = latest_completed_candles(
                candles,
                interval_minutes=interval_minutes,
                limit=max(required_bars, 20),
            )

            swing_highs = self._swing_highs(
                completed,
                lookback=self._settings.swing_lookback,
            )
            swing_lows = self._swing_lows(
                completed,
                lookback=self._settings.swing_lookback,
            )

            structure = self._market_structure(
                swing_highs,
                swing_lows,
            )
            bos = self._break_of_structure(
                completed,
                swing_highs,
                swing_lows,
            )

            timeframe_results[timeframe] = {
                "swing_highs": swing_highs,
                "swing_lows": swing_lows,
                "market_structure": structure,
                "bos": bos,
                "choch": None,
                "opening_range": self._opening_range(
                    completed,
                    minutes=self._settings.opening_range_minutes,
                ),
                "complete": structure is not None,
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
            "day": 1440,
        }

        if timeframe not in rules:
            raise ValueError(f"Unsupported timeframe: {timeframe!r}. Supported: {sorted(rules)}")

        return rules[timeframe]

    @staticmethod
    def _swing_highs(
        candles: list[Any],
        *,
        lookback: int,
    ) -> list[float]:
        highs: list[float] = []

        for index in range(lookback, len(candles) - lookback):
            center = candles[index].high
            left = [candles[i].high for i in range(index - lookback, index)]
            right = [candles[i].high for i in range(index + 1, index + lookback + 1)]

            if center > max(left) and center > max(right):
                highs.append(center)

        return highs

    @staticmethod
    def _swing_lows(
        candles: list[Any],
        *,
        lookback: int,
    ) -> list[float]:
        lows: list[float] = []

        for index in range(lookback, len(candles) - lookback):
            center = candles[index].low
            left = [candles[i].low for i in range(index - lookback, index)]
            right = [candles[i].low for i in range(index + 1, index + lookback)]

            if center < min(left) and center < min(right):
                lows.append(center)

        return lows

    @staticmethod
    def _market_structure(
        swing_highs: list[float],
        swing_lows: list[float],
    ) -> str | None:
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return None

        higher_high = swing_highs[-1] > swing_highs[-2]
        higher_low = swing_lows[-1] > swing_lows[-2]
        lower_high = swing_highs[-1] < swing_highs[-2]
        lower_low = swing_lows[-1] < swing_lows[-2]

        if higher_high and higher_low:
            return "HH_HL"

        if lower_high and lower_low:
            return "LH_LL"

        return "RANGE"

    @staticmethod
    def _break_of_structure(
        candles: list[Any],
        swing_highs: list[float],
        swing_lows: list[float],
    ) -> str | None:
        if not candles:
            return None

        latest_close = candles[-1].close

        if swing_highs and latest_close > swing_highs[-1]:
            return "BULLISH_BOS"

        if swing_lows and latest_close < swing_lows[-1]:
            return "BEARISH_BOS"

        return None

    @staticmethod
    def _opening_range(
        candles: list[Any],
        *,
        minutes: int,
    ) -> dict[str, Any] | None:
        if not candles:
            return None

        session_start = candles[0].bucket_start.replace(
            hour=9,
            minute=15,
            second=0,
            microsecond=0,
        )

        opening_candles = [
            candle
            for candle in candles
            if session_start <= candle.bucket_start < session_start + timedelta(minutes=minutes)
        ]

        if not opening_candles:
            return None

        return {
            "high": max(candle.high for candle in opening_candles),
            "low": min(candle.low for candle in opening_candles),
            "complete": len(opening_candles) == minutes,
        }
