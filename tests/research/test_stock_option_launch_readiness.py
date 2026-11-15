"""Tests for stock-option paper strategy launch readiness."""

from __future__ import annotations

from nse_quant.research.stock_option_launch_readiness import (
    LaunchReadinessSettings,
    classify_launch_readiness,
    evaluate_launch_readiness,
)


def _liquid():
    return {"tradable": True, "failures": []}


def _event_clear():
    return {"block_new_entry": False, "failures": []}


def _defined_risk_valid():
    return {"valid": True, "failures": []}


def _execution_good():
    return {"tradeable": True, "failures": []}


def test_ready_when_all_pass():
    result = evaluate_launch_readiness(
        liquidity_result=_liquid(),
        event_risk_result=_event_clear(),
        defined_risk_result=_defined_risk_valid(),
        execution_quality_result=_execution_good(),
    )
    assert result["ready"] is True
    assert result["failures"] == []
    assert result["decision_eligibility_asserted"] is False


def test_liquidity_failure_blocks():
    result = evaluate_launch_readiness(
        liquidity_result={"tradable": False, "failures": ["spread_too_wide"]},
        event_risk_result=_event_clear(),
        defined_risk_result=_defined_risk_valid(),
        execution_quality_result=_execution_good(),
    )
    assert result["ready"] is False
    assert "liquidity_not_tradable" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_event_risk_failure_blocks():
    result = evaluate_launch_readiness(
        liquidity_result=_liquid(),
        event_risk_result={"block_new_entry": True, "failures": []},
        defined_risk_result=_defined_risk_valid(),
        execution_quality_result=_execution_good(),
    )
    assert result["ready"] is False
    assert "event_risk_blocks_entry" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_defined_risk_failure_blocks():
    result = evaluate_launch_readiness(
        liquidity_result=_liquid(),
        event_risk_result=_event_clear(),
        defined_risk_result={"valid": False, "failures": ["wing_width_out_of_range"]},
        execution_quality_result=_execution_good(),
    )
    assert result["ready"] is False
    assert "defined_risk_structure_invalid" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_execution_quality_failure_blocks():
    result = evaluate_launch_readiness(
        liquidity_result=_liquid(),
        event_risk_result=_event_clear(),
        defined_risk_result=_defined_risk_valid(),
        execution_quality_result={"tradeable": False, "failures": ["slippage_too_high_or_missing"]},
    )
    assert result["ready"] is False
    assert "execution_quality_not_tradeable" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_missing_result_blocks():
    result = evaluate_launch_readiness(
        liquidity_result=None,
        event_risk_result=None,
        defined_risk_result=None,
        execution_quality_result=None,
    )
    assert result["ready"] is False
    assert len(result["failures"]) == 4
    assert result["decision_eligibility_asserted"] is False


def test_classify_ready():
    result = evaluate_launch_readiness(
        liquidity_result=_liquid(),
        event_risk_result=_event_clear(),
        defined_risk_result=_defined_risk_valid(),
        execution_quality_result=_execution_good(),
    )
    assert classify_launch_readiness(result) == "READY"


def test_classify_conditional():
    result = evaluate_launch_readiness(
        liquidity_result=_liquid(),
        event_risk_result=_event_clear(),
        defined_risk_result=_defined_risk_valid(),
        execution_quality_result={"tradeable": False, "failures": ["slippage_too_high_or_missing"]},
    )
    assert classify_launch_readiness(result) == "CONDITIONAL"


def test_classify_not_ready():
    result = evaluate_launch_readiness(
        liquidity_result=None,
        event_risk_result=None,
        defined_risk_result=None,
        execution_quality_result=None,
    )
    assert classify_launch_readiness(result) == "NOT_READY"


def test_settings_defaults():
    settings = LaunchReadinessSettings()
    assert settings.require_liquidity is True
    assert settings.require_event_risk_clear is True
    assert settings.require_defined_risk_valid is True
    assert settings.require_execution_quality_good is True
