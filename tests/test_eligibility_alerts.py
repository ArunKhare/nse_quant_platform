from nse_quant.ops.eligibility_alerts import EligibilityAlertManager


class FakeDecisions:
    def __init__(self):
        self.events = []

    def save_system_event(self, run_id, event_type, payload):
        self.events.append((run_id, event_type, payload))


def test_blocked_eligibility_alerts_once():
    decisions = FakeDecisions()
    manager = EligibilityAlertManager(decisions)

    eligibility = {
        "passed": False,
        "reason": "iv_regime_not_allowed",
        "details": {"current_regime": "UNKNOWN"},
    }

    first = manager.evaluate(
        run_id="run-1",
        eligibility=eligibility,
        notify=lambda message: None,
    )
    second = manager.evaluate(
        run_id="run-1",
        eligibility=eligibility,
        notify=lambda message: None,
    )

    assert first is not None
    assert second is None
    assert len(decisions.events) == 1
    assert decisions.events[0][1] == "strategy_eligibility_blocked"


def test_recovery_alerts_after_blocked_state():
    decisions = FakeDecisions()
    manager = EligibilityAlertManager(decisions)
    notify_messages: list[str] = []

    blocked = {
        "passed": False,
        "reason": "iv_rank_unavailable",
        "details": {},
    }
    eligible = {
        "passed": True,
        "reason": "eligible_regime_source=configured_profile",
        "details": {},
    }

    manager.evaluate(
        run_id="run-1",
        eligibility=blocked,
        notify=notify_messages.append,
    )
    manager.evaluate(
        run_id="run-1",
        eligibility=eligible,
        notify=notify_messages.append,
    )

    assert len(decisions.events) == 2
    assert decisions.events[-1][1] == "strategy_eligibility_recovered"
    assert len(notify_messages) == 2
