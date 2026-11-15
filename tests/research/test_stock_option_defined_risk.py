"""Tests for stock-option defined-risk strategies."""

from __future__ import annotations

from nse_quant.research.stock_option_defined_risk import (
    DefinedRiskSettings,
    evaluate_bear_put_spread,
    evaluate_bull_call_spread,
    evaluate_iron_condor,
    evaluate_iron_fly,
)


def test_bull_call_spread_valid():
    result = evaluate_bull_call_spread(
        long_strike=100.0,
        short_strike=110.0,
        long_premium=5.0,
        short_premium=2.0,
    )
    assert result["valid"] is True
    assert result["wing_width"] == 10.0
    assert result["net_debit"] == 3.0
    assert result["max_profit"] == 7.0
    assert result["max_loss"] == 3.0
    assert result["decision_eligibility_asserted"] is False


def test_bull_call_spread_invalid_strike_order():
    result = evaluate_bull_call_spread(
        long_strike=110.0,
        short_strike=100.0,
        long_premium=5.0,
        short_premium=2.0,
    )
    assert result["valid"] is False
    assert "long_strike_must_be_below_short_strike" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_bear_put_spread_valid():
    result = evaluate_bear_put_spread(
        long_strike=110.0,
        short_strike=100.0,
        long_premium=5.0,
        short_premium=2.0,
    )
    assert result["valid"] is True
    assert result["wing_width"] == 10.0
    assert result["net_debit"] == 3.0
    assert result["max_profit"] == 7.0
    assert result["max_loss"] == 3.0
    assert result["decision_eligibility_asserted"] is False


def test_bear_put_spread_invalid_strike_order():
    result = evaluate_bear_put_spread(
        long_strike=100.0,
        short_strike=110.0,
        long_premium=5.0,
        short_premium=2.0,
    )
    assert result["valid"] is False
    assert "long_strike_must_be_above_short_strike" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_iron_condor_valid():
    result = evaluate_iron_condor(
        put_long_strike=90.0,
        put_short_strike=100.0,
        call_short_strike=110.0,
        call_long_strike=120.0,
        net_credit=3.0,
    )
    assert result["valid"] is True
    assert result["put_wing_width"] == 10.0
    assert result["call_wing_width"] == 10.0
    assert result["net_credit"] == 3.0
    assert result["max_loss"] == 7.0
    assert result["decision_eligibility_asserted"] is False


def test_iron_condor_invalid_wing_order():
    result = evaluate_iron_condor(
        put_long_strike=100.0,
        put_short_strike=90.0,
        call_short_strike=120.0,
        call_long_strike=110.0,
        net_credit=3.0,
    )
    assert result["valid"] is False
    assert "put_long_strike_must_be_below_put_short_strike" in result["failures"]
    assert "call_short_strike_must_be_below_call_long_strike" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_iron_fly_valid():
    result = evaluate_iron_fly(
        put_long_strike=90.0,
        center_strike=100.0,
        call_long_strike=110.0,
        net_credit=3.0,
    )
    assert result["valid"] is True
    assert result["put_wing_width"] == 10.0
    assert result["call_wing_width"] == 10.0
    assert result["net_credit"] == 3.0
    assert result["max_loss"] == 7.0
    assert result["decision_eligibility_asserted"] is False


def test_iron_fly_invalid_wing_order():
    result = evaluate_iron_fly(
        put_long_strike=100.0,
        center_strike=90.0,
        call_long_strike=95.0,
        net_credit=3.0,
    )
    assert result["valid"] is False
    assert "put_long_strike_must_be_below_center_strike" in result["failures"]
    assert "call_long_strike_must_be_above_center_strike" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_settings_defaults():
    settings = DefinedRiskSettings()
    assert settings.max_wing_width == 500.0
    assert settings.min_wing_width == 1.0
    assert settings.require_liquid_wings is True
