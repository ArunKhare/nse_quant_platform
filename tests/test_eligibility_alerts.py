from nse_quant.market_data.replay_provider import ReplayMarketDataProvider
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


def test_eligibility_gate_result_is_persisted(decision_loop_environment, replay_snapshots):
    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(provider)
    loop.settings.research.enforce_strategy_eligibility = True

    result = loop.run_once()

    row = loop.store.conn.execute(
        """
        SELECT gate, passed, reason
        FROM gate_results
        WHERE run_id = ? AND gate = 'strategy_eligibility'
        ORDER BY ts DESC
        LIMIT 1
        """,
        [loop.run_id],
    ).fetchone()

    assert result["status"] == "strategy_eligibility_rejected"
    assert row is not None
    assert row[0] == "strategy_eligibility"
    assert row[1] is False
    assert row[2]


def test_eligibility_rejection_persists_gate_result(
    decision_loop_environment,
    replay_snapshots,
):
    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(
        provider,
        proposal=replay_snapshots["proposal"],
    )
    loop.settings.research.enforce_strategy_eligibility = True

    result = loop.run_once()

    assert result["status"] == "strategy_eligibility_rejected"

    rows = loop.store.conn.execute(
        """
        SELECT gate, passed, reason
        FROM gate_results
        WHERE gate = 'strategy_eligibility'
        ORDER BY ts DESC
        LIMIT 1
        """
    ).fetchall()

    assert rows
    assert rows[0][0] == "strategy_eligibility"
    assert rows[0][1] is False
    assert rows[0][2] == result["rejection_reason"]
