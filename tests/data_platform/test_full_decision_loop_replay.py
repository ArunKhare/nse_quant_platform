"""Tests for exact replay of the full decision loop."""

from __future__ import annotations

from nse_quant.data_platform.full_decision_loop_replay import (
    AnalyticsOutcome,
    FullLoopRequest,
    GateOutputs,
    PortfolioRiskOutcome,
    replay_full_decision_loop,
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
    evaluators = {
        stage: (lambda inputs: inputs)
        for stage in (
            "kill_switch",
            "safety_boundary",
            "publication_admission",
            "native_inputs",
            "strategy",
            "portfolio_risk",
            "execution",
        )
    }
    evaluators["strategy"] = _replay_strategy
    return FullLoopRequest(
        gates=_gates(),
        analytics=_analytics(),
        portfolio_risk=_risk(),
        evaluators=evaluators,
    )


def test_full_loop_replayable():
    result = replay_full_decision_loop(request=_request())
    assert result.replayable is True
    assert result.reason == "FULL_LOOP_REPLAYABLE"
    assert result.integrated.approved is True
    assert result.audited.recorded is True
    assert len(result.replayed) == 7
    assert all(r.outcome_matches for r in result.replayed)
    assert result.decision_eligibility_asserted is False


def test_replay_mismatch_not_replayable():
    request = _request()
    request.evaluators["strategy"] = lambda inputs: dict(mismatch=True)
    result = replay_full_decision_loop(request=request)
    assert result.replayable is False
    assert result.reason == "FULL_LOOP_NOT_REPLAYABLE"
    strategy_result = next(r for r in result.replayed if r.stage == "strategy")
    assert strategy_result.outcome_matches is False


def test_invalid_stage_input_not_replayable():
    request = _request()
    request.gates = "not_gates"
    result = replay_full_decision_loop(request=request)
    assert result.replayable is False
    assert result.reason == "FULL_LOOP_NOT_REPLAYABLE"
    assert result.audited is None


def test_invalid_request_refused():
    result = replay_full_decision_loop(request="not_a_request")
    assert result.replayable is False
    assert result.reason == "INVALID_REQUEST"


def test_seven_stages_replayed():
    result = replay_full_decision_loop(request=_request())
    assert len(result.replayed) == 7
    assert [r.stage for r in result.replayed] == [
        "kill_switch",
        "safety_boundary",
        "publication_admission",
        "native_inputs",
        "strategy",
        "portfolio_risk",
        "execution",
    ]
