"""Institutional regime price-action component.

Classifies completed-candle price action into one of six states for the
institutional regime plugin. Observational only; never grants decision
eligibility or enables live trading.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InstitutionalRegimePriceActionSettings(BaseModel):
    range_band_pct: float = Field(default=0.10, gt=0.0, le=1.0)


STATES = (
    "TREND_UP",
    "TREND_DOWN",
    "RANGE_UPPER",
    "RANGE_MIDDLE",
    "RANGE_LOWER",
    "INSUFFICIENT_DATA",
)


def compute_price_action(
    *,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    settings: InstitutionalRegimePriceActionSettings,
) -> dict[str, Any]:
    if not closes or not highs or not lows:
        return {
            "available": False,
            "complete": False,
            "state": "INSUFFICIENT_DATA",
            "reason": "no_candles",
            "decision_eligibility_asserted": False,
        }

    if not (len(closes) == len(highs) == len(lows)):
        return {
            "available": False,
            "complete": False,
            "state": "INSUFFICIENT_DATA",
            "reason": "candle_length_mismatch",
            "decision_eligibility_asserted": False,
        }

    if len(closes) < 2:
        return {
            "available": False,
            "complete": False,
            "state": "INSUFFICIENT_DATA",
            "reason": "insufficient_history",
            "decision_eligibility_asserted": False,
        }

    first = closes[0]
    last = closes[-1]
    period_high = max(highs)
    period_low = min(lows)

    if period_high <= period_low:
        return {
            "available": False,
            "complete": False,
            "state": "INSUFFICIENT_DATA",
            "reason": "degenerate_range",
            "decision_eligibility_asserted": False,
        }

    change = last - first
    period_range = period_high - period_low
    band = period_range * settings.range_band_pct
    trend_threshold = max(band, period_range * (1.0 - 2.0 * settings.range_band_pct))
    edge_band_pct = min(2.0 * settings.range_band_pct, 0.5)

    if change > trend_threshold:
        state = "TREND_UP"
    elif change < -trend_threshold:
        state = "TREND_DOWN"
    else:
        position = (last - period_low) / period_range
        if position > 1.0 - edge_band_pct:
            state = "RANGE_UPPER"
        elif position < edge_band_pct:
            state = "RANGE_LOWER"
        else:
            state = "RANGE_MIDDLE"

    return {
        "available": True,
        "complete": True,
        "state": state,
        "period_high": period_high,
        "period_low": period_low,
        "change": change,
        "band": band,
        "decision_eligibility_asserted": False,
    }
