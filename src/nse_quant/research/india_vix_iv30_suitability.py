"""Research-only paired assessment of India VIX against NIFTY option-surface IV30.

This evaluator measures proxy error on synchronized, source-pinned observations.
It cannot approve model suitability, publish a feature, or grant decision authority.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from statistics import median
from typing import Any, Sequence

from nse_quant.analytics.constant_maturity_inputs import VERSION as SURFACE_VERSION

VERSION = "india_vix_iv30_proxy_suitability@1"
MINIMUM_PAIRS = 60
MINIMUM_HOLDOUT_PAIRS = 20
MINIMUM_SESSIONS = 20
DEFAULT_MAX_PAIR_GAP_SECONDS = 30.0


@dataclass(frozen=True)
class ProxyPair:
    """One synchronized NIFTY India-VIX / option-surface IV30 observation."""

    trade_date: date
    as_of: datetime
    india_vix_iv30: float
    india_vix_source_time: datetime
    india_vix_received_at: datetime
    india_vix_revision_sha256: str
    surface_iv30: float
    surface_source_time: datetime
    surface_received_at: datetime
    surface_batch_sha256: str
    surface_version: str = SURFACE_VERSION
    surface_iv_source: str = "internal_cm"
    surface_mode: str = "observation"
    surface_decision_eligibility_asserted: bool = False
    underlying: str = "NIFTY"


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field}_AWARE_DATETIME_REQUIRED")
    return value.astimezone(UTC)


def _pin(value: str, field: str) -> None:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError(f"{field}_SHA256_REQUIRED")


def _positive(value: float, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0.0
    ):
        raise ValueError(f"{field}_FINITE_POSITIVE_REQUIRED")
    return float(value)


def _metrics(pairs: Sequence[ProxyPair]) -> dict[str, Any]:
    errors = [float(pair.india_vix_iv30) - float(pair.surface_iv30) for pair in pairs]
    absolute = [abs(value) for value in errors]
    vix_values = [float(pair.india_vix_iv30) for pair in pairs]
    surface_values = [float(pair.surface_iv30) for pair in pairs]
    mean_x = sum(surface_values) / len(surface_values)
    mean_y = sum(vix_values) / len(vix_values)
    covariance = sum(
        (x - mean_x) * (y - mean_y)
        for x, y in zip(surface_values, vix_values, strict=True)
    )
    variance_x = sum((x - mean_x) ** 2 for x in surface_values)
    variance_y = sum((y - mean_y) ** 2 for y in vix_values)
    correlation = (
        covariance / math.sqrt(variance_x * variance_y)
        if variance_x > 0.0 and variance_y > 0.0
        else None
    )
    slope = covariance / variance_x if variance_x > 0.0 else None
    intercept = mean_y - slope * mean_x if slope is not None else None
    return {
        "pairs": len(pairs),
        "bias_vix_minus_surface": sum(errors) / len(errors),
        "mae": sum(absolute) / len(absolute),
        "rmse": math.sqrt(sum(value * value for value in errors) / len(errors)),
        "median_absolute_error": median(absolute),
        "p90_absolute_error": _quantile(absolute, 0.90),
        "correlation": correlation,
        "ols_slope_vix_on_surface": slope,
        "ols_intercept": intercept,
    }


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def evaluate_india_vix_iv30_proxy(
    pairs: Sequence[ProxyPair],
    *,
    max_pair_gap_seconds: float = DEFAULT_MAX_PAIR_GAP_SECONDS,
    holdout_fraction: float = 0.30,
) -> dict[str, Any]:
    """Return descriptive and chronological holdout diagnostics, never approval.

    Pairs must already be assembled from exact retained source revisions. This
    function validates supplied lineage pins and causal clocks, but does not
    authenticate source files, reconstruct the surface, or establish historical
    availability of the supplied records.
    """
    if not isinstance(pairs, Sequence) or isinstance(pairs, (str, bytes)):
        raise ValueError("PROXY_PAIR_SEQUENCE_REQUIRED")
    if len(pairs) < 2:
        raise ValueError("AT_LEAST_TWO_MATCHED_PAIRS_REQUIRED")
    if (
        isinstance(max_pair_gap_seconds, bool)
        or not isinstance(max_pair_gap_seconds, (int, float))
        or not math.isfinite(max_pair_gap_seconds)
        or max_pair_gap_seconds <= 0.0
    ):
        raise ValueError("POSITIVE_PAIR_GAP_REQUIRED")
    if (
        isinstance(holdout_fraction, bool)
        or not isinstance(holdout_fraction, (int, float))
        or not math.isfinite(holdout_fraction)
        or not 0.1 <= holdout_fraction <= 0.5
    ):
        raise ValueError("HOLDOUT_FRACTION_OUT_OF_RANGE")

    previous_as_of: datetime | None = None
    seen_instants: set[datetime] = set()
    normalized: list[ProxyPair] = []
    for pair in pairs:
        if not isinstance(pair, ProxyPair):
            raise ValueError("PROXY_PAIR_TYPE_REQUIRED")
        if pair.underlying != "NIFTY":
            raise ValueError("NIFTY_PROXY_COMPARISON_ONLY")
        if (
            pair.surface_version != SURFACE_VERSION
            or pair.surface_iv_source != "internal_cm"
            or pair.surface_mode != "observation"
            or pair.surface_decision_eligibility_asserted is not False
        ):
            raise ValueError("INTERNAL_CM_OBSERVATION_SURFACE_REQUIRED")
        if not isinstance(pair.trade_date, date) or isinstance(pair.trade_date, datetime):
            raise ValueError("TRADE_DATE_REQUIRED")
        as_of = _utc(pair.as_of, "as_of")
        vix_source = _utc(pair.india_vix_source_time, "india_vix_source_time")
        vix_received = _utc(pair.india_vix_received_at, "india_vix_received_at")
        surface_source = _utc(pair.surface_source_time, "surface_source_time")
        surface_received = _utc(pair.surface_received_at, "surface_received_at")
        if not vix_source <= vix_received <= as_of or not surface_source <= surface_received <= as_of:
            raise ValueError("FUTURE_OR_UNORDERED_SOURCE_CLOCK")
        if abs((vix_source - surface_source).total_seconds()) > max_pair_gap_seconds:
            raise ValueError("SYNCHRONIZED_SOURCE_PAIR_REQUIRED")
        if as_of in seen_instants or (previous_as_of is not None and as_of <= previous_as_of):
            raise ValueError("STRICTLY_ORDERED_UNIQUE_AS_OF_REQUIRED")
        seen_instants.add(as_of)
        previous_as_of = as_of
        _positive(pair.india_vix_iv30, "INDIA_VIX_IV30")
        _positive(pair.surface_iv30, "SURFACE_IV30")
        _pin(pair.india_vix_revision_sha256, "INDIA_VIX_REVISION")
        _pin(pair.surface_batch_sha256, "SURFACE_BATCH")
        normalized.append(pair)

    holdout_count = max(MINIMUM_HOLDOUT_PAIRS, math.ceil(len(normalized) * holdout_fraction))
    if holdout_count >= len(normalized):
        holdout_count = max(1, math.ceil(len(normalized) * holdout_fraction))
    split = len(normalized) - holdout_count
    calibration = normalized[:split]
    holdout = normalized[split:]
    sessions = len({pair.trade_date for pair in normalized})
    sufficient = (
        len(normalized) >= MINIMUM_PAIRS
        and len(holdout) >= MINIMUM_HOLDOUT_PAIRS
        and sessions >= MINIMUM_SESSIONS
        and bool(calibration)
    )
    return {
        "version": VERSION,
        "assessment_status": "DIAGNOSTIC_ONLY_REVIEW_REQUIRED" if sufficient else "INSUFFICIENT_EVIDENCE",
        "suitability_asserted": False,
        "decision_eligibility_asserted": False,
        "publication_asserted": False,
        "underlying": "NIFTY",
        "proxy": "india_vix",
        "benchmark": "internal_cm_black76_iv30",
        "error_convention": "india_vix_iv30_minus_surface_iv30",
        "volatility_units": "annualized_decimal",
        "max_pair_gap_seconds": float(max_pair_gap_seconds),
        "holdout_fraction_requested": float(holdout_fraction),
        "sample": {
            "pairs": len(normalized),
            "sessions": sessions,
            "calibration_pairs": len(calibration),
            "holdout_pairs": len(holdout),
            "first_as_of": _utc(normalized[0].as_of, "as_of").isoformat(),
            "last_as_of": _utc(normalized[-1].as_of, "as_of").isoformat(),
        },
        "all_sample_metrics": _metrics(normalized),
        "calibration_metrics": _metrics(calibration) if calibration else None,
        "holdout_metrics": _metrics(holdout),
        "limitations": [
            "descriptive_proxy_comparison_not_model_approval",
            "source_pins_are_validated_but_source_artifacts_are_not_replayed_here",
            "historical_availability_and_cross_store_atomicity_are_not_asserted",
            "no_vrp_or_decision_loop_authority",
        ],
    }
