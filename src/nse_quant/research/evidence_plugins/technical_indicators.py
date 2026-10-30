"""Look-ahead-safe technical-indicator evidence from completed candles."""

from __future__ import annotations

from typing import Any

from nse_quant.research.candle_resampler import (
    latest_completed_candles,
)
from nse_quant.research.evidence_plugins.base import (
    DecisionContext,
    EvidencePlugin,
)


class TechnicalIndicatorsPlugin(EvidencePlugin):
    name = "technical_indicators"

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

        timeframe_results: dict[str, Any] = {}

        for timeframe in self._settings.timeframes:
            interval_minutes = self._interval_minutes(timeframe)
            required_bars = max(self._settings.ema_periods)

            completed = latest_completed_candles(
                candles,
                interval_minutes=interval_minutes,
                limit=required_bars,
            )

            closes = [candle.close for candle in completed]
            highs = [candle.high for candle in completed]
            lows = [candle.low for candle in completed]

            rsi = self._rsi(closes, period=self._settings.rsi_period)
            macd = self._macd(closes)
            ema_values = {
                f"ema{period}": self._ema(closes, period) for period in self._settings.ema_periods
            }

            atr = self._atr(highs, lows, closes, period=14)
            momentum = self._atr_normalized_momentum(
                closes,
                atr,
            )

            ema20 = ema_values.get("ema20")
            ema20_distance = (
                (closes[-1] - ema20) / ema20 if ema20 is not None and ema20 != 0 else None
            )

            timeframe_results[timeframe] = {
                "rsi": rsi,
                "macd": macd,
                "stochastic_rsi": None,
                "adx": None,
                "ema": ema_values,
                "ema_alignment": self._ema_alignment(ema_values),
                "atr_normalized_momentum": momentum,
                "ema20_distance": ema20_distance,
                "rsi_divergence": None,
                "complete": (
                    rsi is not None
                    and macd is not None
                    and ema_values.get("ema20") is not None
                    and momentum is not None
                ),
                "required_bars": required_bars,
                "available_bars": len(completed),
            }

        complete = all(result["complete"] for result in timeframe_results.values())

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
    def _ema(
        values: list[float],
        period: int,
    ) -> float | None:
        if len(values) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period

        for value in values[period:]:
            ema = (value - ema) * multiplier + ema

        return ema

    @classmethod
    def _rsi(
        cls,
        values: list[float],
        *,
        period: int,
    ) -> float | None:
        if len(values) < period + 1:
            return None

        gains: list[float] = []
        losses: list[float] = []

        for index in range(1, len(values)):
            change = values[index] - values[index - 1]
            gains.append(max(change, 0.0))
            losses.append(max(-change, 0.0))

        average_gain = sum(gains[:period]) / period
        average_loss = sum(losses[:period]) / period

        for index in range(period, len(gains)):
            average_gain = (average_gain * (period - 1) + gains[index]) / period
            average_loss = (average_loss * (period - 1) + losses[index]) / period

        if average_loss == 0:
            return 100.0

        relative_strength = average_gain / average_loss
        return 100 - (100 / (1 + relative_strength))

    @classmethod
    def _macd(
        cls,
        values: list[float],
    ) -> dict[str, float] | None:
        fast = cls._ema(values, 12)
        slow = cls._ema(values, 26)

        if fast is None or slow is None:
            return None

        macd_line = fast - slow

        macd_history: list[float] = []
        for index in range(26, len(values) + 1):
            fast_value = cls._ema(values[:index], 12)
            slow_value = cls._ema(values[:index], 26)

            if fast_value is None or slow_value is None:
                continue

            macd_history.append(fast_value - slow_value)

        signal = cls._ema(macd_history, 9)

        if signal is None:
            return None

        return {
            "macd": macd_line,
            "signal": signal,
            "histogram": macd_line - signal,
        }

    @staticmethod
    def _atr(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        *,
        period: int,
    ) -> float | None:
        if len(highs) < period + 1:
            return None

        true_ranges: list[float] = []

        for index in range(1, len(highs)):
            high = highs[index]
            low = lows[index]
            previous_close = closes[index - 1]

            true_ranges.append(
                max(
                    high - low,
                    abs(high - previous_close),
                    abs(low - previous_close),
                )
            )

        return sum(true_ranges[-period:]) / period

    @staticmethod
    def _atr_normalized_momentum(
        closes: list[float],
        atr: float | None,
    ) -> float | None:
        if atr is None or atr <= 0 or len(closes) < 2:
            return None

        return (closes[-1] - closes[-2]) / atr

    @staticmethod
    def _ema_alignment(
        ema_values: dict[str, float | None],
    ) -> str | None:
        ema20 = ema_values.get("ema20")
        ema50 = ema_values.get("ema50")

        if ema20 is None or ema50 is None:
            return None

        if ema20 > ema50:
            return "BULLISH"

        if ema20 < ema50:
            return "BEARISH"

        return "NEUTRAL"
