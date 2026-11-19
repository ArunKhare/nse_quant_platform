"""Tests for stock-option event-risk rules."""

from __future__ import annotations

from nse_quant.research.stock_option_event_risk import (
    EventRiskRules,
    evaluate_event_risk,
)


def test_no_event_risk():
    result = evaluate_event_risk(
        event_date="2025-06-15",
        as_of_date="2025-06-01",
        days_to_event=14,
        days_since_event=999,
    )
    assert result["block_new_entry"] is False
    assert result["reduce_size"] is False
    assert result["size_reduction_factor"] == 1.0
    assert result["decision_eligibility_asserted"] is False


def test_within_blackout_before():
    result = evaluate_event_risk(
        event_date="2025-06-15",
        as_of_date="2025-06-13",
        days_to_event=2,
        days_since_event=999,
    )
    assert result["block_new_entry"] is True
    assert result["reduce_size"] is True
    assert "block_new_entry" in result["actions"]
    assert "reduce_size" in result["actions"]
    assert result["decision_eligibility_asserted"] is False


def test_within_blackout_after():
    result = evaluate_event_risk(
        event_date="2025-06-15",
        as_of_date="2025-06-16",
        days_to_event=999,
        days_since_event=1,
    )
    assert result["block_new_entry"] is True
    assert result["reduce_size"] is True
    assert "block_new_entry" in result["actions"]
    assert result["decision_eligibility_asserted"] is False


def test_near_event_reduces_size():
    result = evaluate_event_risk(
        event_date="2025-06-15",
        as_of_date="2025-06-10",
        days_to_event=5,
        days_since_event=999,
    )
    assert result["block_new_entry"] is False
    assert result["reduce_size"] is True
    assert result["size_reduction_factor"] == 0.5
    assert result["decision_eligibility_asserted"] is False


def test_missing_inputs_fail():
    result = evaluate_event_risk(
        event_date=None,
        as_of_date=None,
        days_to_event=None,
        days_since_event=None,
    )
    assert result["block_new_entry"] is False
    assert result["reduce_size"] is False
    assert len(result["failures"]) == 4
    assert result["decision_eligibility_asserted"] is False


def test_short_volatility_blocked():
    result = evaluate_event_risk(
        event_date="2025-06-15",
        as_of_date="2025-06-13",
        days_to_event=2,
        days_since_event=999,
    )
    assert "block_short_volatility" in result["actions"]
    assert result["decision_eligibility_asserted"] is False


def test_settings_defaults():
    settings = EventRiskRules()
    assert settings.blackout_days_before == 3
    assert settings.blackout_days_after == 1
    assert settings.size_reduction_factor == 0.5
    assert settings.block_short_volatility is True
