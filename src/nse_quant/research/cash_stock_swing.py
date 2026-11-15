"""Cash-stock swing strategy signal generator; research-only, no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class CashStockSwingSettings:
    sma_short: int = 50
    sma_long: int = 200
    breakout_days: int = 20
    rvol_threshold: float = 1.5
    atr_period: int = 14
    stop_atr_multiple: float = 2.0
    target_r_multiple: float = 2.0
    time_stop_days: int = 10
    min_history: int = 220


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def compute_rvol(volume: pd.Series, baseline_periods: int = 30) -> pd.Series:
    """Relative volume: current volume divided by the mean of the PRIOR baseline_periods rows (excluding current)."""
    baseline = volume.shift(1).rolling(window=baseline_periods, min_periods=baseline_periods).mean()
    return volume / baseline


def generate_signal(
    *,
    candles: pd.DataFrame,
    settings: CashStockSwingSettings | None = None,
    event_risk_active: bool = False,
) -> dict[str, Any]:
    """Generate a cash-stock swing signal from completed daily candles.

    candles must have columns: date, open, high, low, close, volume, sorted ascending by date.
    Returns a signal dict with entry/stop/target/time-stop/event-filter and decision_eligibility_asserted=False.
    """
    settings = settings or CashStockSwingSettings()
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(candles.columns):
        return {
            "available": False,
            "reason": "missing_candle_columns",
            "decision_eligibility_asserted": False,
        }
    if len(candles) < settings.min_history:
        return {
            "available": False,
            "reason": "insufficient_history",
            "decision_eligibility_asserted": False,
        }
    close = candles["close"]
    high = candles["high"]
    low = candles["low"]
    volume = candles["volume"]

    sma_short = compute_sma(close, settings.sma_short)
    sma_long = compute_sma(close, settings.sma_long)
    atr = compute_atr(high, low, close, settings.atr_period)
    rvol = compute_rvol(volume)

    last = candles.iloc[-1]
    prior_high = high.iloc[-(settings.breakout_days + 1) : -1].max()
    entry_price = float(last["close"])
    stop_price = entry_price - settings.stop_atr_multiple * float(atr.iloc[-1])
    risk = entry_price - stop_price
    target_price = entry_price + settings.target_r_multiple * risk

    trend_ok = bool(sma_short.iloc[-1] > sma_long.iloc[-1])
    breakout_ok = bool(entry_price > prior_high)
    volume_ok = bool(rvol.iloc[-1] >= settings.rvol_threshold)
    entry_signal = trend_ok and breakout_ok and volume_ok and not event_risk_active

    return {
        "available": True,
        "entry_signal": entry_signal,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "time_stop_days": settings.time_stop_days,
        "event_filter_active": event_risk_active,
        "trend_ok": trend_ok,
        "breakout_ok": breakout_ok,
        "volume_ok": volume_ok,
        "decision_eligibility_asserted": False,
    }
