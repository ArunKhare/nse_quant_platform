"""Observation-only v5 classification of prepared daily/surface features.

Provisional rules: ouput/research.md sections 3.1-3.4. This module does not
compute or fetch IV surfaces, daily indicators, or published Gold artifacts.
It must not be wired into entry eligibility before calibration and approval.
No v4 label translation or legacy-table fallback is provided.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from nse_quant.core.constants import IST
from nse_quant.core.iv_statistics import iv_percentile_and_rank
from nse_quant.core.regime_registry import (
    REGIME_REGISTRY_VERSION,
    REGIMES,
    IvState,
    PriceAction,
    Skew,
    TermStructure,
)

VERSION = "institutional_regime_v5_provisional_2"


@dataclass(frozen=True)
class DailyValue:
    session: date
    value: float
    source: str


@dataclass(frozen=True)
class PriceDiagnostics:
    session: date
    adx14: float
    er20: float
    chop14: float
    atr_percentile: float
    bandwidth_percentile: float
    range_position: float
    change20: float
    sma20_slope: float
    di_difference: float


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _history(rows: tuple[DailyValue, ...], *, today: date, source: str, minimum: int, positive: bool) -> list[float]:
    sessions = [row.session for row in rows]
    if sessions != sorted(set(sessions)):
        raise ValueError("daily_history_must_be_unique_and_ordered")
    if any(
        row.session >= today or row.source != source or not math.isfinite(row.value) or (positive and row.value <= 0)
        for row in rows
    ):
        raise ValueError("invalid_daily_history_or_source")
    if len(rows) < minimum:
        raise ValueError("insufficient_daily_history")
    return [row.value for row in rows[-252:]]


def _price(d: PriceDiagnostics) -> tuple[PriceAction, float]:
    values = asdict(d)
    if any(not math.isfinite(float(v)) for k, v in values.items() if k != "session"):
        raise ValueError("non_finite_price_diagnostics")
    if not (
        0 <= d.adx14 <= 100
        and 0 <= d.er20 <= 1
        and 0 <= d.chop14 <= 100
        and 0 <= d.atr_percentile <= 100
        and 0 <= d.bandwidth_percentile <= 100
        and 0 <= d.range_position <= 1
    ):
        raise ValueError("invalid_price_diagnostics_range")
    if d.atr_percentile >= 70 and (d.adx14 < 20 or d.chop14 > 61.8) and d.er20 < 0.22:
        choppy = max((20 - d.adx14) / 20, (d.chop14 - 61.8) / 38.2)
        return PriceAction.HIGH_VOL_CHOP, min((d.atr_percentile - 70) / 30, choppy, (0.22 - d.er20) / 0.22)
    if d.adx14 >= 25 and d.er20 >= 0.35:
        direction = (
            1
            if min(d.change20, d.sma20_slope, d.di_difference) > 0
            else (-1 if max(d.change20, d.sma20_slope, d.di_difference) < 0 else 0)
        )
        if direction:
            state = PriceAction.STRONG_BULL_TREND if direction > 0 else PriceAction.STRONG_BEAR_TREND
            return state, min((d.adx14 - 25) / 75, (d.er20 - 0.35) / 0.65)
    if d.bandwidth_percentile <= 10 and d.atr_percentile <= 30:
        return PriceAction.COMPRESSION, min((10 - d.bandwidth_percentile) / 10, (30 - d.atr_percentile) / 30)
    if d.adx14 < 25:
        state = PriceAction.RANGE_HIGH if d.range_position >= 0.5 else PriceAction.RANGE_LOW
        return state, min((25 - d.adx14) / 25, abs(d.range_position - 0.5) * 2)
    raise ValueError("price_action_indeterminate")


def classify(
    *,
    as_of: datetime,
    surface_time: datetime,
    iv30: float,
    iv90: float,
    iv30_source: str,
    eod_iv_close: DailyValue,
    eod_iv_history: tuple[DailyValue, ...],
    rr25: float,
    rr25_source: str,
    rr25_history: tuple[DailyValue, ...],
    previous_close: PriceDiagnostics,
    latest_close: PriceDiagnostics,
    previous_iv_state: IvState | None = None,
    previous_skew: Skew | None = None,
    minimum_confidence: float = 0.0,
    max_surface_age_seconds: float = 90.0,
) -> dict[str, Any]:
    """Classify prepared features, not raw candles or ATM put/call gaps.

    Caller supplies consecutive completed trading-session diagnostics (ADX
    Wilder14, ER20, CHOP14, ATR252 percentile, BandWidth120 percentile and
    range60 position). RR25 uses 30D Black-76 call25 IV minus put25 IV.
    IVP compares the selected completed India VIX EOD close with prior EOD
    closes; IVR includes that selected close in its rolling window. Structural
    term classification uses internal constant-maturity IV30/IV90 only. Live
    India VIX is deliberately not accepted by this classifier. IVs use decimals.
    Two matching daily candidates confirm a price state; transitional states
    remain unavailable rather than carrying forward an unconfirmed label.
    """
    result: dict[str, Any] = {
        "available": False,
        "complete": False,
        "regime_label": None,
        "classifier_version": VERSION,
        "regime_version": REGIME_REGISTRY_VERSION,
        "as_of": as_of.isoformat(),
        "mode": "observation",
        "decision_eligibility_asserted": False,
        "thresholds_provisional": True,
        "input_provenance": {
            "iv30_source": iv30_source,
            "iv90_source": "internal_cm",
            "eod_iv30_source": "india_vix_eod",
            "eod_iv_close": asdict(eod_iv_close),
            "rr25_source": rr25_source,
            "rr25_convention": "black76_call25_minus_put25_30d",
            "surface_time": surface_time.isoformat(),
            "previous_close": asdict(previous_close),
            "latest_close": asdict(latest_close),
            "eod_iv_history": [asdict(row) for row in eod_iv_history],
            "rr25_history": [asdict(row) for row in rr25_history],
        },
    }
    try:
        if as_of.utcoffset() is None or surface_time.utcoffset() is None:
            raise ValueError("timezone_aware_timestamps_required")
        if not math.isfinite(max_surface_age_seconds) or max_surface_age_seconds <= 0:
            raise ValueError("invalid_surface_age_limit")
        age = (as_of - surface_time).total_seconds()
        if age < 0 or age > max_surface_age_seconds:
            raise ValueError("future_or_stale_surface")
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("invalid_confidence_floor")
        if iv30_source != "internal_cm" or not rr25_source:
            raise ValueError("unsupported_feature_source")
        if not isinstance(eod_iv_close, DailyValue):
            raise ValueError("typed_eod_iv30_close_required")
        if (
            not all(math.isfinite(x) for x in (iv30, iv90, eod_iv_close.value, rr25))
            or min(iv30, iv90, eod_iv_close.value) <= 0
        ):
            raise ValueError("invalid_surface_values")
        if previous_iv_state is not None and not isinstance(previous_iv_state, IvState):
            raise ValueError("invalid_previous_iv_state")
        if previous_skew is not None and not isinstance(previous_skew, Skew):
            raise ValueError("invalid_previous_skew")
        today = as_of.astimezone(IST).date()
        if not previous_close.session < latest_close.session < today:
            raise ValueError("completed_ordered_daily_features_required")
        eod_ivs = _history(
            eod_iv_history, today=today, source="india_vix_eod", minimum=120, positive=True
        )
        eod_age = (today - eod_iv_close.session).days
        if (
            eod_iv_close.source != "india_vix_eod"
            or not 1 <= eod_age <= 4
            or (eod_iv_history and eod_iv_history[-1].session >= eod_iv_close.session)
        ):
            raise ValueError("completed_recent_eod_iv30_required")
        rrs = _history(rr25_history, today=today, source=rr25_source, minimum=40, positive=False)
        ivp, ivr, _ = iv_percentile_and_rank(eod_ivs, eod_iv_close.value)
        iv_state = IvState.HIGH_IV if ivp >= (60 if previous_iv_state is IvState.HIGH_IV else 70) else IvState.LOW_IV
        slope = iv30 - iv90
        term = (
            TermStructure.CONTANGO
            if slope < -0.005
            else (TermStructure.BACKWARDATION if slope > 0.005 else TermStructure.FLAT_TERM)
        )
        skew = (
            Skew.FORWARD_REVERSE_SKEW
            if rr25 > 0
            else (
                Skew.HIGH_PUT_SKEW
                if rr25 <= _percentile(rrs, 0.1)
                or (previous_skew is Skew.HIGH_PUT_SKEW and rr25 <= _percentile(rrs, 0.5))
                else Skew.NORMAL_SKEW
            )
        )
        old_candidate, old_confidence = _price(previous_close)
        candidate, confidence = _price(latest_close)
        if candidate != old_candidate:
            raise ValueError("price_action_awaiting_second_close")
        confidence = max(0.0, min(1.0, confidence, old_confidence))
        if confidence < minimum_confidence:
            raise ValueError("price_action_confidence_below_floor")
        label = f"{iv_state}_{term}_{skew}_{candidate}"
        definition = REGIMES[label]
        result.update(
            {
                "available": True,
                "complete": True,
                "regime_label": label,
                "regime_id": definition.regime_id,
                "reason": None,
                "regime_components": {
                    "iv_state": iv_state.value,
                    "term_structure": term.value,
                    "skew": skew.value,
                    "price_action": candidate.value,
                },
                "price_action_confidence": confidence,
                "diagnostics": {
                    "ivp": ivp,
                    "ivr": ivr,
                    "ivp_ivr_divergence": abs(ivp - ivr) > 30 if ivr is not None else None,
                    "iv30_minus_iv90": slope,
                    "eod_iv30": eod_iv_close.value,
                },
            }
        )
    except ValueError as exc:
        result["reason"] = str(exc)
    return result
