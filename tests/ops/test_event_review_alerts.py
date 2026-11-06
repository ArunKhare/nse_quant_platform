"""Tests for stateful event-review alerts."""

from __future__ import annotations

from types import SimpleNamespace

from nse_quant.ops.event_review_alerts import EventReviewAlertManager
from nse_quant.risk.event_risk_policy import EventRiskDecision


class FakeDecisions:
    def __init__(self):
        self.events = []

    def save_system_event(self, *, run_id, event_type, payload, proposal=None):
        self.events.append((run_id, event_type, payload))
        return "event-id"


def build_manager():
    decisions = FakeDecisions()
    return EventReviewAlertManager(decisions), decisions


def review_decision():
    return EventRiskDecision(
        action="REVIEW_OPEN_POSITIONS",
        size_multiplier=1.0,
        reasons=["iv_crush_after_event"],
    )


def test_alerts_once_on_review_with_open_positions():
    manager, decisions = build_manager()
    notified: list[str] = []
    result = manager.evaluate(
        run_id="run-1",
        decision=review_decision(),
        open_positions=[SimpleNamespace(strategy_position_id="p1")],
        notify=notified.append,
    )
    assert result is not None
    assert result["open_position_count"] == 1
    assert decisions.events[0][1] == "event_review_alert"
    assert len(notified) == 1

    second = manager.evaluate(
        run_id="run-1",
        decision=review_decision(),
        open_positions=[SimpleNamespace(strategy_position_id="p1")],
        notify=notified.append,
    )
    assert second is None
    assert len(notified) == 1


def test_no_alert_without_open_positions():
    manager, decisions = build_manager()
    result = manager.evaluate(
        run_id="run-1",
        decision=review_decision(),
        open_positions=[],
        notify=None,
    )
    assert result is None
    assert decisions.events == []


def test_no_alert_for_other_actions():
    manager, decisions = build_manager()
    result = manager.evaluate(
        run_id="run-1",
        decision=EventRiskDecision(action="OBSERVE", size_multiplier=1.0),
        open_positions=[SimpleNamespace(strategy_position_id="p1")],
        notify=None,
    )
    assert result is None
    assert decisions.events == []


def test_alert_rearms_after_non_review_action():
    manager, decisions = build_manager()
    positions = [SimpleNamespace(strategy_position_id="p1")]
    manager.evaluate(
        run_id="run-1", decision=review_decision(), open_positions=positions, notify=None
    )
    manager.evaluate(
        run_id="run-1",
        decision=EventRiskDecision(action="OBSERVE", size_multiplier=1.0),
        open_positions=positions,
        notify=None,
    )
    result = manager.evaluate(
        run_id="run-1",
        decision=review_decision(),
        open_positions=positions,
        notify=None,
    )
    assert result is not None
    assert len(decisions.events) == 2


def test_none_decision_is_ignored():
    manager, decisions = build_manager()
    assert (
        manager.evaluate(
            run_id="run-1",
            decision=None,
            open_positions=[SimpleNamespace(strategy_position_id="p1")],
            notify=None,
        )
        is None
    )
    assert decisions.events == []
