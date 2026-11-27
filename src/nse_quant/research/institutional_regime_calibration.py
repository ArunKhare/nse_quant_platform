"""Diagnostic-only walk-forward calibration report for provisional regime thresholds.

The report freezes the provisional rules, measures their training-window
distributions, and evaluates state frequencies and HAR-RV errors on later
sessions. It never selects replacement thresholds or grants decision authority.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any

from nse_quant.research.har_realized_volatility import (
    HAR_TRAINING_WINDOW,
    calibrate_har_rv_forecast_errors,
    forecast_har_rv_30d,
)
from nse_quant.research.institutional_regime_price_action_v5 import (
    _Metrics,
    _classify,
)

CALIBRATION_REPORT_VERSION = "institutional_regime_walk_forward_calibration_v1"
DEFAULT_TRAINING_SESSIONS = 360
DEFAULT_TEST_SESSIONS = 63
DEFAULT_STEP_SESSIONS = 63
TERM_FLAT_BAND = 0.005
IV_HIGH_ENTRY = 70.0
IV_HIGH_EXIT = 60.0
PRICE_ACTION_THRESHOLDS = {
    "adx_trend_entry": 25.0,
    "adx_trend_exit": 20.0,
    "er20_trend_entry": 0.35,
    "er20_noise_floor": 0.22,
    "chop14_choppy": 61.8,
    "atr_percentile_high": 70.0,
    "bandwidth_percentile_compression": 10.0,
    "atr_percentile_compression": 30.0,
    "range_position_boundary": 0.5,
    "confidence_floor": 0.0,
    "persistence_closes": 2,
}


@dataclass(frozen=True)
class CalibrationObservation:
    """One NIFTY completed-session row with point-in-time prepared diagnostics."""

    session: date
    ivp: float
    iv30_minus_iv90: float
    rr25: float
    adx14: float
    plus_di14: float
    minus_di14: float
    er20: float
    chop14: float
    atr14: float
    atr_percentile: float
    bandwidth_percentile: float
    range_position: float
    change20: float
    sma20_slope: float
    realized_variance: float


def _finite(value: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}
    ordered = sorted(values)

    def at(fraction: float) -> float:
        position = (len(ordered) - 1) * fraction
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    return {f"p{int(fraction * 100)}": at(fraction) for fraction in (0.1, 0.25, 0.5, 0.75, 0.9)}


def _distribution(values: list[str]) -> dict[str, Any]:
    counts = Counter(values)
    total = len(values)
    return {
        "count": total,
        "counts": dict(sorted(counts.items())),
        "fractions": {
            key: count / total for key, count in sorted(counts.items())
        } if total else {},
    }


def _iv_state(value: float, previous: str) -> str:
    if value >= IV_HIGH_ENTRY:
        return "HIGH_IV"
    if value < IV_HIGH_EXIT:
        return "LOW_IV"
    return previous


def _skew_state(value: float, p10: float, p50: float, previous: str) -> str:
    if value > 0:
        return "FORWARD_REVERSE_SKEW"
    if value <= p10 or (previous == "HIGH_PUT_SKEW" and value <= p50):
        return "HIGH_PUT_SKEW"
    return "NORMAL_SKEW"


def _price_metrics(row: CalibrationObservation) -> _Metrics:
    return _Metrics(
        adx=row.adx14,
        plus_di=row.plus_di14,
        minus_di=row.minus_di14,
        er20=row.er20,
        chop14=row.chop14,
        atr14=row.atr14,
        atr_percentile=row.atr_percentile,
        bandwidth_percentile=row.bandwidth_percentile,
        range_position=row.range_position,
        change20=row.change20,
        sma20_slope=row.sma20_slope,
    )


def _validate_observations(rows: list[CalibrationObservation]) -> str | None:
    if len(rows) < 2:
        return "insufficient_observations"
    sessions = [row.session for row in rows]
    if sessions != sorted(set(sessions)):
        return "sessions_must_be_unique_and_ordered"
    for row in rows:
        values = (
            row.ivp, row.iv30_minus_iv90, row.rr25, row.adx14, row.plus_di14,
            row.minus_di14, row.er20, row.chop14, row.atr14,
            row.atr_percentile, row.bandwidth_percentile, row.range_position,
            row.change20, row.sma20_slope, row.realized_variance,
        )
        if not all(_finite(value) for value in values):
            return "non_finite_calibration_input"
        if not 0 <= row.ivp <= 100 or not 0 <= row.adx14 <= 100:
            return "invalid_ivp_or_adx_range"
        if not 0 <= row.plus_di14 <= 100 or not 0 <= row.minus_di14 <= 100:
            return "invalid_directional_indicator_range"
        if not 0 <= row.er20 <= 1 or not 0 <= row.chop14 <= 100:
            return "invalid_efficiency_or_choppiness_range"
        if not 0 <= row.atr_percentile <= 100 or not 0 <= row.bandwidth_percentile <= 100:
            return "invalid_volatility_percentile_range"
        if not 0 <= row.range_position <= 1 or row.atr14 < 0 or row.realized_variance < 0:
            return "invalid_range_position_or_variance"
    return None


def _fold_report(
    train: list[CalibrationObservation],
    test: list[CalibrationObservation],
    *,
    fold_id: int,
) -> dict[str, Any]:
    train_ivp = [row.ivp for row in train]
    train_term = [row.iv30_minus_iv90 for row in train]
    train_rr25 = [row.rr25 for row in train]
    train_price = {
        "adx14": [row.adx14 for row in train],
        "er20": [row.er20 for row in train],
        "chop14": [row.chop14 for row in train],
        "atr_percentile": [row.atr_percentile for row in train],
        "bandwidth_percentile": [row.bandwidth_percentile for row in train],
        "range_position": [row.range_position for row in train],
    }
    iv_previous = "LOW_IV"
    for value in train_ivp:
        iv_previous = _iv_state(value, iv_previous)
    skew_previous = "NORMAL_SKEW"
    for index, row in enumerate(train):
        prior_rr25 = [item.rr25 for item in train[:index]][-252:]
        if len(prior_rr25) >= 40:
            prior_quantiles = _quantiles(prior_rr25)
            prior_p10 = prior_quantiles["p10"]
            prior_p50 = prior_quantiles["p50"]
            assert prior_p10 is not None and prior_p50 is not None
            skew_previous = _skew_state(row.rr25, prior_p10, prior_p50, skew_previous)

    iv_states: list[str] = []
    term_states: list[str] = []
    skew_states: list[str] = []
    price_states: list[str] = []
    price_unavailable = 0
    oos_skew_p10: list[float] = []
    oos_skew_p50: list[float] = []
    confirmed_price_state: str | None = None
    candidate_price_state: str | None = None
    candidate_price_count = 0
    confirmed_price_confidence = 0.0
    for row in train:
        raw_price_state, raw_confidence = _classify(_price_metrics(row), confirmed_price_state)
        if raw_price_state is None:
            candidate_price_state = None
            candidate_price_count = 0
        elif raw_price_state == candidate_price_state:
            candidate_price_count += 1
        else:
            candidate_price_state = raw_price_state
            candidate_price_count = 1
        if candidate_price_state is not None and candidate_price_count >= 2:
            confirmed_price_state = candidate_price_state
            confirmed_price_confidence = raw_confidence

    price_confidences: list[float] = []
    for index, row in enumerate(test):
        iv_previous = _iv_state(row.ivp, iv_previous)
        iv_states.append(iv_previous)
        term_states.append(
            "CONTANGO" if row.iv30_minus_iv90 < -TERM_FLAT_BAND
            else ("BACKWARDATION" if row.iv30_minus_iv90 > TERM_FLAT_BAND else "FLAT_TERM")
        )
        point_in_time_rr25 = [item.rr25 for item in train + test[:index]][-252:]
        if len(point_in_time_rr25) >= 40:
            point_in_time_quantiles = _quantiles(point_in_time_rr25)
            point_p10 = point_in_time_quantiles["p10"]
            point_p50 = point_in_time_quantiles["p50"]
            assert point_p10 is not None and point_p50 is not None
            oos_skew_p10.append(point_p10)
            oos_skew_p50.append(point_p50)
            skew_previous = _skew_state(row.rr25, point_p10, point_p50, skew_previous)
            skew_states.append(skew_previous)

        raw_price_state, raw_confidence = _classify(_price_metrics(row), confirmed_price_state)
        if raw_price_state is None:
            candidate_price_state = None
            candidate_price_count = 0
        elif raw_price_state == candidate_price_state:
            candidate_price_count += 1
        else:
            candidate_price_state = raw_price_state
            candidate_price_count = 1
        if raw_price_state is None:
            price_unavailable += 1
            continue
        if candidate_price_state is not None and candidate_price_count >= 2:
            confirmed_price_state = candidate_price_state
            confirmed_price_confidence = raw_confidence
        elif raw_price_state == confirmed_price_state and confirmed_price_state is not None:
            confirmed_price_confidence = raw_confidence
        if confirmed_price_state is None:
            price_unavailable += 1
        else:
            price_states.append(confirmed_price_state)
            price_confidences.append(confirmed_price_confidence)

    train_rv = [row.realized_variance for row in train]
    test_rv = [row.realized_variance for row in test]
    har_calibration = calibrate_har_rv_forecast_errors(train_rv)
    # Calibration sufficiency is diagnostic here; this report cannot enable a gate.
    har_calibration["calibration_sample_sufficient_for_review"] = bool(
        har_calibration.get("gate_margin_eligible")
    )
    har_calibration["gate_margin_eligible"] = False
    har_calibration["diagnostic_only"] = True
    har_forecast, har_details = forecast_har_rv_30d(train_rv)
    har_oos: dict[str, Any] = {
        "available": False,
        "horizon_sessions": 21,
        "forecast_reason": har_details.get("reason"),
        "realized_test_sessions": min(len(test_rv), 21),
        "absolute_annualized_variance_error": None,
    }
    if har_forecast is not None and len(test_rv) >= 21:
        forecast_variance = har_forecast * har_forecast
        realized_variance = sum(test_rv[:21]) / 21 * 252
        har_oos.update({
            "available": True,
            "forecast_annualized_volatility": har_forecast,
            "forecast_annualized_variance": forecast_variance,
            "realized_annualized_variance": realized_variance,
            "absolute_annualized_variance_error": abs(realized_variance - forecast_variance),
        })

    return {
        "fold_id": fold_id,
        "train": {"start": train[0].session.isoformat(), "end": train[-1].session.isoformat(), "sessions": len(train)},
        "test": {"start": test[0].session.isoformat(), "end": test[-1].session.isoformat(), "sessions": len(test)},
        "threshold_stability": {
            "ivp": {**_quantiles(train_ivp), "provisional_entry": IV_HIGH_ENTRY, "provisional_exit": IV_HIGH_EXIT},
            "iv30_minus_iv90": {**_quantiles(train_term), "provisional_flat_band": TERM_FLAT_BAND},
            "rr25": {**_quantiles(train_rr25), "oos_high_put_cutoff": _quantiles(oos_skew_p10), "oos_hysteresis_cutoff": _quantiles(oos_skew_p50)},
            "price_action_diagnostics": {key: _quantiles(values) for key, values in train_price.items()},
            "price_action_provisional_thresholds": PRICE_ACTION_THRESHOLDS,
        },
        "out_of_sample_state_distributions": {
            "iv_state": _distribution(iv_states),
            "term_structure": _distribution(term_states),
            "skew": _distribution(skew_states),
            "price_action": {
                **_distribution(price_states),
                "unavailable_sessions": price_unavailable,
                "confidence_quantiles": _quantiles(price_confidences),
            },
        },
        "har_rv": {
            "training_error_calibration": har_calibration,
            "out_of_sample_forecast": har_oos,
        },
    }


def build_institutional_regime_calibration_report(
    observations: list[CalibrationObservation],
    *,
    underlying: str = "NIFTY",
    source_manifest: dict[str, str] | None = None,
    training_sessions: int = DEFAULT_TRAINING_SESSIONS,
    test_sessions: int = DEFAULT_TEST_SESSIONS,
    step_sessions: int = DEFAULT_STEP_SESSIONS,
) -> dict[str, Any]:
    """Build a chronological rolling-window report; thresholds remain unchanged."""
    report: dict[str, Any] = {
        "version": CALIBRATION_REPORT_VERSION,
        "underlying": underlying,
        "mode": "diagnostic_only",
        "thresholds_changed": False,
        "thresholds_promoted": False,
        "decision_eligibility_asserted": False,
        "paper_trading_approval_asserted": False,
        "source_manifest": source_manifest or {},
        "configuration": {
            "training_sessions": training_sessions,
            "test_sessions": test_sessions,
            "step_sessions": step_sessions,
            "fold_type": "rolling_fixed_length_sessions",
        },
        "provisional_thresholds": {
            "ivp_high_entry": IV_HIGH_ENTRY,
            "ivp_high_exit": IV_HIGH_EXIT,
            "term_flat_band": TERM_FLAT_BAND,
            "price_action": PRICE_ACTION_THRESHOLDS,
            "rr25_high_put_quantile": 0.10,
            "rr25_high_put_exit_quantile": 0.50,
        },
        "sample": {"observations": len(observations)},
        "folds": [],
        "summary": {},
    }
    invalid = _validate_observations(observations)
    if underlying != "NIFTY":
        invalid = "calibration_underlying_must_be_NIFTY"
    if training_sessions < max(HAR_TRAINING_WINDOW + 22, 324) or test_sessions < 21 or step_sessions < test_sessions:
        invalid = "invalid_fold_configuration"
    if invalid:
        report["status"] = "INSUFFICIENT_OR_INVALID_EVIDENCE"
        report["reason"] = invalid
        return report

    folds: list[dict[str, Any]] = []
    start = 0
    while start + training_sessions + test_sessions <= len(observations):
        train_start = start
        test_start = start + training_sessions
        test_end = test_start + test_sessions
        folds.append(_fold_report(
            observations[train_start:test_start],
            observations[test_start:test_end],
            fold_id=len(folds),
        ))
        start += step_sessions

    if not folds:
        report["status"] = "INSUFFICIENT_OR_INVALID_EVIDENCE"
        report["reason"] = "no_complete_train_test_fold"
        return report

    har_errors = [
        fold["har_rv"]["out_of_sample_forecast"]["absolute_annualized_variance_error"]
        for fold in folds
        if fold["har_rv"]["out_of_sample_forecast"]["available"]
    ]
    report["folds"] = folds
    report["sample"].update({
        "first_session": observations[0].session.isoformat(),
        "last_session": observations[-1].session.isoformat(),
        "fold_count": len(folds),
    })
    report["summary"] = {
        "iv_state": _distribution([
            state for fold in folds for state, count in fold["out_of_sample_state_distributions"]["iv_state"]["counts"].items()
            for _ in range(count)
        ]),
        "term_structure": _distribution([
            state for fold in folds for state, count in fold["out_of_sample_state_distributions"]["term_structure"]["counts"].items()
            for _ in range(count)
        ]),
        "skew": _distribution([
            state for fold in folds for state, count in fold["out_of_sample_state_distributions"]["skew"]["counts"].items()
            for _ in range(count)
        ]),
        "price_action": _distribution([
            state for fold in folds for state, count in fold["out_of_sample_state_distributions"]["price_action"]["counts"].items()
            for _ in range(count)
        ]),
        "har_rv_oos_forecast_error": {
            "available_folds": len(har_errors),
            "mean_absolute_annualized_variance_error": (
                sum(har_errors) / len(har_errors) if har_errors else None
            ),
        },
    }
    report["status"] = "DIAGNOSTIC_REPORT_COMPLETE"
    return report


def render_calibration_report_markdown(report: dict[str, Any]) -> str:
    """Render a compact human-readable report without implying promotion."""
    lines = [
        "# Institutional regime walk-forward calibration",
        "",
        f"- Version: {report.get('version')}",
        f"- Underlying: {report.get('underlying')}",
        f"- Status: {report.get('status')}",
        f"- Mode: {report.get('mode')}",
        f"- Thresholds changed/promoted: {report.get('thresholds_changed')}/{report.get('thresholds_promoted')}",
        f"- Decision eligibility asserted: {report.get('decision_eligibility_asserted')}",
        "",
        "## Sample and fold design",
        "",
        f"- Sample: {report.get('sample')}",
        f"- Configuration: {report.get('configuration')}",
        f"- Source manifest: {report.get('source_manifest')}",
        "",
        "## Summary",
        "",
        f"`{report.get('summary')}`",
        "",
        "## Fold detail",
        "",
    ]
    for fold in report.get("folds", []):
        lines.extend([
            f"### Fold {fold['fold_id']}",
            "",
            f"- Train: {fold['train']}",
            f"- Test: {fold['test']}",
            f"- Threshold stability: `{fold['threshold_stability']}`",
            f"- Out-of-sample state distributions: `{fold['out_of_sample_state_distributions']}`",
            f"- HAR-RV: `{fold['har_rv']}`",
            "",
        ])
    lines.extend([
        "## Governance",
        "",
        "- Provisional thresholds are reported, not optimized or replaced.",
        "- All state distributions and forecast errors are out of sample.",
        "- HAR-RV training error calibration is computed only inside each training window.",
        "- No result in this report grants publication, paper-trading, decision, or execution authority.",
        "- Threshold promotion requires a separately reviewed decision and a versioned classifier/configuration change.",
        "",
    ])
    return "\n".join(lines)
