"""Tests for native analytics input validation."""

from __future__ import annotations

from nse_quant.data_platform.analytics_input_validation import (
    AnalyticsInputSchema,
    validate_analytics_inputs,
)


def _schema():
    return AnalyticsInputSchema()


def _valid_inputs():
    return dict(
        feature_names=["iv_rank", "iv_rv_spread"],
        thresholds=dict(min_credit=0.5, max_spread=0.1),
        history_window=30,
        cold_start_policy="reject",
    )


def test_valid_inputs_pass():
    result = validate_analytics_inputs(inputs=_valid_inputs(), schema=_schema())
    assert result.valid is True
    assert result.reasons == []
    assert len(result.checks) == 4


def test_invalid_feature_names_refused():
    inputs = _valid_inputs()
    inputs["feature_names"] = "not_a_list"
    result = validate_analytics_inputs(inputs=inputs, schema=_schema())
    assert result.valid is False
    assert "INVALID_FEATURE_NAMES" in result.reasons


def test_invalid_thresholds_refused():
    inputs = _valid_inputs()
    inputs["thresholds"] = dict(min_credit="not_a_number")
    result = validate_analytics_inputs(inputs=inputs, schema=_schema())
    assert result.valid is False
    assert "INVALID_THRESHOLDS" in result.reasons


def test_invalid_history_window_refused():
    inputs = _valid_inputs()
    inputs["history_window"] = -1
    result = validate_analytics_inputs(inputs=inputs, schema=_schema())
    assert result.valid is False
    assert "INVALID_HISTORY_WINDOW" in result.reasons


def test_invalid_cold_start_refused():
    inputs = _valid_inputs()
    inputs["cold_start_policy"] = "invalid"
    result = validate_analytics_inputs(inputs=inputs, schema=_schema())
    assert result.valid is False
    assert "INVALID_COLD_START_POLICY" in result.reasons


def test_non_dict_refused():
    result = validate_analytics_inputs(inputs="not_a_dict", schema=_schema())
    assert result.valid is False
    assert "INVALID_INPUTS" in result.reasons
