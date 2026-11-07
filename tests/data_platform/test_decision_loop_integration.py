"""Tests for decision-loop integration."""

from __future__ import annotations

from nse_quant.data_platform.decision_loop_integration import (
    AnalyticsOutcome,
    DecisionLoopRequest,
    GateOutputs,
    PortfolioRiskOutcome,
    run_decision_loop,
)
from nse_quant.data_platform.strategy_evaluation_integration import (
    integrate_strategy_evaluation,
)


def _gates():
    return GateOutputs(
        market_session_passed=True,
        iv_regime_passed=True,
        expected_move_passed=True,
        liquidity_passed=True,
    )


def _analytics():
    return AnalyticsOutcome(valid=True)


def _risk():
    return PortfolioRiskOutcome(approved=True)


def _replay_strategy(inputs: dict) -> dict:
    return integrate_strategy_evaluation(
        gates=GateOutputs.model_validate(inputs["gates"]),
        analytics=AnalyticsOutcome.model_validate(inputs["analytics"]),
        portfolio_risk=PortfolioRiskOutcome.model_validate(inputs["portfolio_risk"]),
    ).model_dump()


def _request():
    return DecisionLoopRequest(
        gates=_gates(),
        analytics=_analytics(),
        portfolio_risk=_risk(),
        evaluators=dict(strategy=_replay_strategy),
    )


def test_full_loop_complete():
    result = run_decision_loop(request=_request())
    assert result.complete is True
    assert result.reason == "DECISION_LOOP_COMPLETE"
    assert result.integrated.approved is True
    assert result.audited.recorded is True
    assert len(result.replayed) == 1
    assert result.replayed[0].outcome_matches is True
    assert result.decision_eligibility_asserted is False


def test_gates_failed_incomplete():
    request = _request()
    request.gates.market_session_passed = False
    result = run_decision_loop(request=request)
    assert result.complete is False
    assert result.reason == "DECISION_LOOP_INCOMPLETE"
    assert result.integrated.approved is False


def test_analytics_invalid_incomplete():
    request = _request()
    request.analytics.valid = False
    result = run_decision_loop(request=request)
    assert result.complete is False
    assert result.reason == "DECISION_LOOP_INCOMPLETE"


def test_risk_not_approved_incomplete():
    request = _request()
    request.portfolio_risk.approved = False
    result = run_decision_loop(request=request)
    assert result.complete is False
    assert result.reason == "DECISION_LOOP_INCOMPLETE"


def test_replay_mismatch_incomplete():
    request = _request()
    request.evaluators = dict(strategy=lambda inputs: dict(mismatch=True))
    result = run_decision_loop(request=request)
    assert result.complete is False
    assert result.reason == "DECISION_LOOP_INCOMPLETE"
    assert result.replayed[0].outcome_matches is False


def test_invalid_request_refused():
    result = run_decision_loop(request="not_a_request")
    assert result.complete is False
    assert result.reason == "INVALID_REQUEST"
