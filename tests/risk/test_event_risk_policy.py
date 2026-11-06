"""Tests for event-aware risk policy."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nse_quant.risk.event_risk_policy import (
    EventRiskDecision,
    EventRiskPolicySettings,
    evaluate_event_risk,
)


def settings(**overrides) -> EventRiskPolicySettings:
    defaults = {
        "enabled": True,
        "reduce_size_on_high_volatility": True,
        "max_size_reduction_pct": 50.0,
        "review_iv_crush_threshold": -0.02,
    }
    defaults.update(overrides)
    return EventRiskPolicySettings(**defaults)


def test_disabled_policy_always_observes():
    decision = evaluate_event_risk(
        event_impact={"block_new_entries": True},
        reaction=None,
        settings=EventRiskPolicySettings(enabled=False),
    )
    assert decision.action == "OBSERVE"
    assert decision.size_multiplier == 1.0
    assert decision.reasons == ["event_risk_policy_disabled"]
    assert decision.decision_eligibility_asserted is False


def test_block_new_entries_sets_zero_multiplier():
    decision = evaluate_event_risk(
        event_impact={"block_new_entries": True},
        reaction=None,
        settings=settings(),
    )
    assert decision.action == "BLOCK_NEW_ENTRIES"
    assert decision.size_multiplier == 0.0
    assert "high_impact_event_within_blackout_window" in decision.reasons


def test_high_volatility_reduces_size_when_enabled():
    decision = evaluate_event_risk(
        event_impact={"volatility_impact": "high"},
        reaction=None,
        settings=settings(),
    )
    assert decision.action == "REDUCE_SIZE"
    assert decision.size_multiplier == 0.5
    assert "high_volatility_event_impact" in decision.reasons


def test_high_volatility_observes_when_reduction_disabled():
    decision = evaluate_event_risk(
        event_impact={"volatility_impact": "high"},
        reaction=None,
        settings=settings(reduce_size_on_high_volatility=False),
    )
    assert decision.action == "OBSERVE"
    assert decision.size_multiplier == 1.0


def test_iv_crush_triggers_review():
    decision = evaluate_event_risk(
        event_impact={"volatility_impact": "medium"},
        reaction={"atm_iv_change": -0.03},
        settings=settings(),
    )
    assert decision.action == "REVIEW_OPEN_POSITIONS"
    assert decision.size_multiplier == 1.0
    assert "iv_crush_after_event" in decision.reasons


def test_no_rule_triggered_observes():
    decision = evaluate_event_risk(
        event_impact={"volatility_impact": "low"},
        reaction={"atm_iv_change": 0.01},
        settings=settings(),
    )
    assert decision.action == "OBSERVE"
    assert decision.size_multiplier == 1.0
    assert decision.reasons == ["no_event_risk_rule_triggered"]


def test_missing_inputs_are_safe():
    decision = evaluate_event_risk(
        event_impact=None,
        reaction=None,
        settings=settings(),
    )
    assert decision.action == "OBSERVE"
    assert decision.size_multiplier == 1.0


@pytest.mark.parametrize(
    ("reduction", "threshold"),
    [(-1.0, -0.02), (101.0, -0.02), (50.0, 0.01)],
)
def test_invalid_settings_are_rejected(reduction: float, threshold: float):
    with pytest.raises(ValidationError):
        EventRiskPolicySettings(
            max_size_reduction_pct=reduction,
            review_iv_crush_threshold=threshold,
        )


def test_decision_model_defaults():
    decision = EventRiskDecision(action="OBSERVE", size_multiplier=1.0)
    assert decision.reasons == []
    assert decision.decision_eligibility_asserted is False
