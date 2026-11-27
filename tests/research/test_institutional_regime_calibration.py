from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta

from nse_quant.research.institutional_regime_calibration import (
    CALIBRATION_REPORT_VERSION,
    CalibrationObservation,
    build_institutional_regime_calibration_report,
    render_calibration_report_markdown,
)


def observations(count: int = 486) -> list[CalibrationObservation]:
    first = date(2024, 1, 1)
    rows = []
    session = first
    for index in range(count):
        while session.weekday() >= 5:
            session += timedelta(days=1)
        rows.append(
            CalibrationObservation(
                session=session,
                ivp=float(45 + (index % 56)),
                iv30_minus_iv90=-0.01 if index % 4 else 0.001,
                rr25=-0.04 + (index % 25) * 0.001,
                adx14=35.0,
                plus_di14=30.0,
                minus_di14=5.0,
                er20=0.6,
                chop14=35.0,
                atr14=2.0,
                atr_percentile=50.0,
                bandwidth_percentile=50.0,
                range_position=0.8,
                change20=10.0,
                sma20_slope=0.5,
                realized_variance=0.0001 * (
                    1.0 + 0.15 * math.sin(index / 7) + 0.08 * math.cos(index / 19)
                ),
            )
        )
        session += timedelta(days=1)
    return rows


def test_walk_forward_report_keeps_thresholds_diagnostic_only() -> None:
    report = build_institutional_regime_calibration_report(
        observations(),
        source_manifest={"daily_features": "nifty_daily_v1", "rv": "nifty_5m_rv_v1"},
    )

    assert report["version"] == CALIBRATION_REPORT_VERSION
    assert report["status"] == "DIAGNOSTIC_REPORT_COMPLETE"
    assert report["mode"] == "diagnostic_only"
    assert report["thresholds_changed"] is False
    assert report["thresholds_promoted"] is False
    assert report["decision_eligibility_asserted"] is False
    assert report["paper_trading_approval_asserted"] is False
    assert report["sample"]["fold_count"] == 2
    assert report["folds"][0]["train"]["end"] < report["folds"][0]["test"]["start"]
    assert report["folds"][0]["test"]["end"] < report["folds"][1]["test"]["start"]
    assert report["folds"][0]["out_of_sample_state_distributions"]["price_action"]["counts"] == {
        "STRONG_BULL_TREND": 63
    }
    assert report["folds"][0]["out_of_sample_state_distributions"]["price_action"]["confidence_quantiles"]["p50"] is not None
    assert "absolute_annualized_variance_error" in report["folds"][0]["har_rv"]["out_of_sample_forecast"]
    assert report["folds"][0]["har_rv"]["training_error_calibration"]["gate_margin_eligible"] is False
    assert report["folds"][0]["har_rv"]["training_error_calibration"]["diagnostic_only"] is True


def test_report_markdown_states_non_promotion_governance() -> None:
    report = build_institutional_regime_calibration_report(observations())
    markdown = render_calibration_report_markdown(report)

    assert "Thresholds changed/promoted: False/False" in markdown
    assert "No result in this report grants publication" in markdown


def test_insufficient_history_fails_closed_without_folds() -> None:
    report = build_institutional_regime_calibration_report(observations(100))

    assert report["status"] == "INSUFFICIENT_OR_INVALID_EVIDENCE"
    assert report["reason"] == "no_complete_train_test_fold"
    assert report["folds"] == []
    assert report["decision_eligibility_asserted"] is False


def test_invalid_order_or_non_nifty_underlying_fails_closed() -> None:
    rows = observations()
    rows[1] = replace(rows[1], session=rows[0].session)
    unordered = build_institutional_regime_calibration_report(rows)
    other_underlying = build_institutional_regime_calibration_report(
        observations(), underlying="BANKNIFTY"
    )

    assert unordered["reason"] == "sessions_must_be_unique_and_ordered"
    assert other_underlying["reason"] == "calibration_underlying_must_be_NIFTY"


def test_overlapping_test_windows_are_rejected() -> None:
    report = build_institutional_regime_calibration_report(
        observations(),
        step_sessions=30,
        test_sessions=63,
    )

    assert report["status"] == "INSUFFICIENT_OR_INVALID_EVIDENCE"
    assert report["reason"] == "invalid_fold_configuration"
