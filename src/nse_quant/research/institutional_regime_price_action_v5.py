"""Daily-bar institutional price-action classifier (v5 component).

The classifier is deterministic and observational. It consumes completed daily
OHLCV bars only and never grants decision or execution eligibility.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from statistics import pstdev
from typing import Any

from pydantic import BaseModel, Field, model_validator


PRICE_ACTION_CLASSIFIER_VERSION = "institutional_daily_price_action_v5"
PRICE_ACTION_STATES = (
    "STRONG_BULL_TREND",
    "STRONG_BEAR_TREND",
    "RANGE_HIGH",
    "RANGE_LOW",
    "COMPRESSION",
    "HIGH_VOL_CHOP",
)


class InstitutionalRegimePriceActionSettings(BaseModel):
    """Versioned, configurable evidence requirements for daily classification."""

    daily_history_limit: int = Field(default=300, ge=266)
    minimum_daily_bars: int = Field(default=266, ge=266)
    confidence_floor: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_history(self) -> InstitutionalRegimePriceActionSettings:
        if self.daily_history_limit < self.minimum_daily_bars:
            raise ValueError("daily_history_limit must be >= minimum_daily_bars")
        return self


@dataclass(frozen=True)
class DailyBar:
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class _Metrics:
    adx: float
    plus_di: float
    minus_di: float
    er20: float
    chop14: float
    atr14: float
    atr_percentile: float
    bandwidth_percentile: float
    range_position: float
    change20: float
    sma20_slope: float


def _unavailable(reason: str, **details: Any) -> dict[str, Any]:
    return {
        "available": False,
        "complete": False,
        "state": None,
        "reason": reason,
        "classifier_version": PRICE_ACTION_CLASSIFIER_VERSION,
        "decision_eligibility_asserted": False,
        **details,
    }


def _percentile_rank(values: list[float], current: float) -> float:
    return 100.0 * sum(value <= current for value in values) / len(values)


def _adx_series(
    bars: list[DailyBar],
    period: int = 14,
) -> tuple[list[float | None], list[float | None], list[float | None], list[float | None]]:
    size = len(bars)
    atr: list[float | None] = [None] * size
    plus_di: list[float | None] = [None] * size
    minus_di: list[float | None] = [None] * size
    adx: list[float | None] = [None] * size
    if size <= period:
        return atr, plus_di, minus_di, adx

    true_ranges: list[float] = [0.0] * size
    positive_dm: list[float] = [0.0] * size
    negative_dm: list[float] = [0.0] * size
    for index in range(1, size):
        bar = bars[index]
        previous_close = bars[index - 1].close
        true_ranges[index] = max(
            bar.high - bar.low,
            abs(bar.high - previous_close),
            abs(bar.low - previous_close),
        )
        up_move = bar.high - bars[index - 1].high
        down_move = bars[index - 1].low - bar.low
        positive_dm[index] = up_move if up_move > down_move and up_move > 0 else 0.0
        negative_dm[index] = down_move if down_move > up_move and down_move > 0 else 0.0

    smooth_tr = sum(true_ranges[1 : period + 1])
    smooth_plus = sum(positive_dm[1 : period + 1])
    smooth_minus = sum(negative_dm[1 : period + 1])
    dx_values: list[float | None] = [None] * size

    for index in range(period, size):
        if index > period:
            smooth_tr = smooth_tr - smooth_tr / period + true_ranges[index]
            smooth_plus = smooth_plus - smooth_plus / period + positive_dm[index]
            smooth_minus = smooth_minus - smooth_minus / period + negative_dm[index]
        atr[index] = smooth_tr / period
        if smooth_tr <= 0:
            continue
        plus_value = 100.0 * smooth_plus / smooth_tr
        minus_value = 100.0 * smooth_minus / smooth_tr
        plus_di[index] = plus_value
        minus_di[index] = minus_value
        denominator = plus_value + minus_value
        if denominator > 0:
            dx_values[index] = 100.0 * abs(plus_value - minus_value) / denominator

    first_dx_index = period
    seed_end = first_dx_index + period
    seed = [value for value in dx_values[first_dx_index:seed_end] if value is not None]
    if len(seed) < period:
        return atr, plus_di, minus_di, adx
    adx_value = sum(seed) / period
    adx[seed_end - 1] = adx_value
    for index in range(seed_end, size):
        dx = dx_values[index]
        if dx is not None:
            adx_value = ((adx_value * (period - 1)) + dx) / period
            adx[index] = adx_value
    return atr, plus_di, minus_di, adx


def _chop14(bars: list[DailyBar], index: int, period: int = 14) -> float | None:
    if index < period:
        return None
    window = bars[index - period + 1 : index + 1]
    tr_sum = 0.0
    for offset, bar in enumerate(window):
        previous_close = bars[index - period + offset].close
        tr_sum += max(
            bar.high - bar.low,
            abs(bar.high - previous_close),
            abs(bar.low - previous_close),
        )
    highest = max(bar.high for bar in window)
    lowest = min(bar.low for bar in window)
    price_range = highest - lowest
    if price_range <= 0 or tr_sum <= 0:
        return None
    return 100.0 * math.log10(tr_sum / price_range) / math.log10(period)


def _bandwidth(bars: list[DailyBar], index: int, period: int = 20) -> float | None:
    if index + 1 < period:
        return None
    closes = [bar.close for bar in bars[index - period + 1 : index + 1]]
    middle = sum(closes) / period
    if middle <= 0:
        return None
    standard_deviation = pstdev(closes)
    return 4.0 * standard_deviation / middle


def _metrics_at(
    bars: list[DailyBar],
    index: int,
    atr_series: list[float | None],
    plus_di_series: list[float | None],
    minus_di_series: list[float | None],
    adx_series: list[float | None],
) -> _Metrics | None:
    if index < 60 or index < 20:
        return None
    adx = adx_series[index]
    plus_di = plus_di_series[index]
    minus_di = minus_di_series[index]
    atr = atr_series[index]
    if adx is None or plus_di is None or minus_di is None or atr is None or atr <= 0:
        return None

    er_denominator = sum(
        abs(bars[position].close - bars[position - 1].close)
        for position in range(index - 19, index + 1)
    )
    er20 = (
        abs(bars[index].close - bars[index - 20].close) / er_denominator
        if er_denominator > 0
        else 0.0
    )
    chop = _chop14(bars, index)
    bandwidth = _bandwidth(bars, index)
    if chop is None or bandwidth is None:
        return None

    atr_values = [value for value in atr_series[max(0, index - 251) : index + 1] if value is not None]
    bandwidth_values = [
        value
        for position in range(max(0, index - 119), index + 1)
        if (value := _bandwidth(bars, position)) is not None
    ]
    if len(atr_values) < 252 or len(bandwidth_values) < 120:
        return None

    range_window = bars[index - 59 : index + 1]
    range_high = max(bar.high for bar in range_window)
    range_low = min(bar.low for bar in range_window)
    if range_high <= range_low:
        return None

    sma20 = sum(bar.close for bar in bars[index - 19 : index + 1]) / 20
    previous_sma20 = sum(bar.close for bar in bars[index - 20 : index]) / 20
    return _Metrics(
        adx=adx,
        plus_di=plus_di,
        minus_di=minus_di,
        er20=er20,
        chop14=chop,
        atr14=atr,
        atr_percentile=_percentile_rank(atr_values, atr),
        bandwidth_percentile=_percentile_rank(bandwidth_values, bandwidth),
        range_position=(bars[index].close - range_low) / (range_high - range_low),
        change20=bars[index].close - bars[index - 20].close,
        sma20_slope=sma20 - previous_sma20,
    )


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def _classify(metrics: _Metrics, prior_state: str | None) -> tuple[str, float]:
    bullish_direction = (
        metrics.change20 > 0
        and metrics.sma20_slope > 0
        and metrics.plus_di > metrics.minus_di
    )
    bearish_direction = (
        metrics.change20 < 0
        and metrics.sma20_slope < 0
        and metrics.minus_di > metrics.plus_di
    )

    # The research specification explicitly defines ADX < 20 as the trend
    # exit threshold. Retain a confirmed trend through the 20–25 neutral band
    # while its directional diagnostics continue to agree.
    if prior_state == "STRONG_BULL_TREND" and metrics.adx >= 20 and bullish_direction:
        confidence = min(
            _clip((metrics.adx - 20.0) / 80.0),
            _clip(metrics.er20 / 0.65),
            _clip((metrics.plus_di - metrics.minus_di) / 100.0),
        )
        return prior_state, confidence
    if prior_state == "STRONG_BEAR_TREND" and metrics.adx >= 20 and bearish_direction:
        confidence = min(
            _clip((metrics.adx - 20.0) / 80.0),
            _clip(metrics.er20 / 0.65),
            _clip((metrics.minus_di - metrics.plus_di) / 100.0),
        )
        return prior_state, confidence

    if (
        metrics.atr_percentile >= 70.0
        and (metrics.adx < 20.0 or metrics.chop14 > 61.8)
        and metrics.er20 < 0.22
    ):
        chop_margin = (
            (20.0 - metrics.adx) / 20.0
            if metrics.adx < 20.0
            else (metrics.chop14 - 61.8) / (100.0 - 61.8)
        )
        confidence = min(
            _clip((metrics.atr_percentile - 70.0) / 30.0),
            _clip(chop_margin),
            _clip((0.22 - metrics.er20) / 0.22),
        )
        return "HIGH_VOL_CHOP", confidence

    if metrics.adx >= 25.0 and metrics.er20 >= 0.35 and (bullish_direction or bearish_direction):
        direction_margin = (
            min(
                _clip(abs(metrics.change20) / (20.0 * metrics.atr14)),
                _clip(abs(metrics.sma20_slope) / metrics.atr14),
                _clip(abs(metrics.plus_di - metrics.minus_di) / 100.0),
            )
        )
        confidence = min(
            _clip((metrics.adx - 25.0) / 75.0),
            _clip((metrics.er20 - 0.35) / 0.65),
            direction_margin,
        )
        return ("STRONG_BULL_TREND" if bullish_direction else "STRONG_BEAR_TREND"), confidence

    if metrics.bandwidth_percentile <= 10.0 and metrics.atr_percentile <= 30.0:
        confidence = min(
            _clip((10.0 - metrics.bandwidth_percentile) / 10.0),
            _clip((30.0 - metrics.atr_percentile) / 30.0),
        )
        return "COMPRESSION", confidence

    if metrics.adx < 25.0:
        if metrics.range_position >= 0.5:
            confidence = min(
                _clip((25.0 - metrics.adx) / 25.0),
                _clip((metrics.range_position - 0.5) / 0.5),
            )
            return "RANGE_HIGH", confidence
        confidence = min(
            _clip((25.0 - metrics.adx) / 25.0),
            _clip((0.5 - metrics.range_position) / 0.5),
        )
        return "RANGE_LOW", confidence

    return "RANGE_HIGH" if metrics.range_position >= 0.5 else "RANGE_LOW", 0.0


def classify_daily_price_action(
    bars: list[DailyBar],
    settings: InstitutionalRegimePriceActionSettings,
) -> dict[str, Any]:
    """Classify the latest completed daily bar using the provisional v5 rules."""
    if len(bars) < settings.minimum_daily_bars:
        return _unavailable(
            "insufficient_daily_history",
            bars_available=len(bars),
            minimum_daily_bars=settings.minimum_daily_bars,
        )
    dates = [bar.trade_date for bar in bars]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        return _unavailable("daily_bars_not_strictly_ordered_unique")
    for bar in bars:
        values = (bar.open, bar.high, bar.low, bar.close, bar.volume)
        if not all(math.isfinite(value) for value in values):
            return _unavailable("non_finite_daily_bar", trade_date=bar.trade_date.isoformat())
        if min(bar.open, bar.high, bar.low, bar.close) <= 0:
            return _unavailable("non_positive_daily_price", trade_date=bar.trade_date.isoformat())
        if bar.high < max(bar.open, bar.close, bar.low) or bar.low > min(bar.open, bar.close, bar.high):
            return _unavailable("invalid_daily_ohlc", trade_date=bar.trade_date.isoformat())
        if bar.volume < 0:
            return _unavailable("negative_daily_volume", trade_date=bar.trade_date.isoformat())

    atr, plus_di, minus_di, adx = _adx_series(bars)
    classified: list[tuple[int, str, float, _Metrics]] = []
    confirmed_state: str | None = None
    candidate_state: str | None = None
    candidate_count = 0
    confirmed_index: int | None = None

    for index in range(len(bars)):
        metrics = _metrics_at(bars, index, atr, plus_di, minus_di, adx)
        if metrics is None:
            continue
        raw_state, confidence = _classify(metrics, confirmed_state)
        if confidence < settings.confidence_floor:
            continue
        if raw_state == candidate_state:
            candidate_count += 1
        else:
            candidate_state = raw_state
            candidate_count = 1
        if candidate_count >= 2:
            confirmed_state = raw_state
            confirmed_index = index
        classified.append((index, raw_state, confidence, metrics))

    if confirmed_state is None or confirmed_index is None:
        latest = classified[-1] if classified else None
        return _unavailable(
            "no_state_confirmed_for_two_consecutive_closes",
            bars_available=len(bars),
            latest_candidate=latest[1] if latest else None,
            latest_candidate_confidence=latest[2] if latest else None,
        )

    latest_index, latest_raw_state, latest_confidence, latest_metrics = classified[-1]
    confirmed_metrics = _metrics_at(bars, confirmed_index, atr, plus_di, minus_di, adx)
    if confirmed_metrics is None:
        return _unavailable("confirmed_state_metrics_unavailable")
    _, confirmed_confidence = _classify(confirmed_metrics, None)
    pending_state = latest_raw_state if latest_raw_state != confirmed_state else None
    output_confidence = latest_confidence if pending_state is None else confirmed_confidence

    return {
        "available": True,
        "complete": True,
        "state": confirmed_state,
        "classifier_version": PRICE_ACTION_CLASSIFIER_VERSION,
        "latest_bar_date": bars[-1].trade_date.isoformat(),
        "confirmed_on": bars[confirmed_index].trade_date.isoformat(),
        "signal_date": bars[confirmed_index].trade_date.isoformat(),
        "bars_available": len(bars),
        "bars_required": settings.minimum_daily_bars,
        "persistence_closes": 2,
        "pending_state": pending_state,
        "confidence": output_confidence,
        "confidence_floor": settings.confidence_floor,
        "diagnostics": {
            "adx14": latest_metrics.adx,
            "plus_di14": latest_metrics.plus_di,
            "minus_di14": latest_metrics.minus_di,
            "er20": latest_metrics.er20,
            "chop14": latest_metrics.chop14,
            "atr14": latest_metrics.atr14,
            "atr_percentile_252": latest_metrics.atr_percentile,
            "bandwidth_percentile_120": latest_metrics.bandwidth_percentile,
            "range_position_60": latest_metrics.range_position,
            "change20": latest_metrics.change20,
            "sma20_slope": latest_metrics.sma20_slope,
        },
        "thresholds": {
            "adx_trend_entry": 25.0,
            "adx_trend_exit": 20.0,
            "er20_trend_entry": 0.35,
            "er20_noise_floor": 0.22,
            "chop14_choppy": 61.8,
            "atr_percentile_high": 70.0,
            "bandwidth_percentile_compression": 10.0,
            "atr_percentile_compression": 30.0,
            "range_position_boundary": 0.5,
        },
        "decision_eligibility_asserted": False,
    }
