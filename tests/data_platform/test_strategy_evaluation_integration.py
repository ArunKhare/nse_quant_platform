"""Tests for strategy evaluation integration."""

from __future__ import annotations

from nse_quant.data_platform.strategy_evaluation_integration import (
    AnalyticsOutcome,
    GateOutputs,
    PortfolioRiskOutcome,
    integrate_strategy_evaluation,
)


def _gates(
    market: bool = True,
    iv: bool = True,
    move: bool = True,
    liquidity: bool = True,
):
    return GateOutputs(
        market_session_passed=market,
        iv_regime_passed=iv,
        expected_move_passed=move,
        liquidity_passed=liquidity,
    )


def _analytics(valid: bool = True):
    return AnalyticsOutcome(valid=valid)


def _risk(approved: bool = True):
    return PortfolioRiskOutcome(approved=approved)


def test_all_pass_approved():
    result = integrate_strategy_evaluation(
        gates=_gates(), analytics=_analytics(), portfolio_risk=_risk()
    )
    assert result.approved is True
    assert result.reasons == []
    assert len(result.checks) == 6
    assert result.decision_eligibility_asserted is False


def test_market_session_failed_refused():
    result = integrate_strategy_evaluation(
        gates=_gates(market=False), analytics=_analytics(), portfolio_risk=_risk()
    )
    assert result.approved is False
    assert "MARKET_SESSION_FAILED" in result.reasons


def test_iv_regime_failed_refused():
    result = integrate_strategy_evaluation(
        gates=_gates(iv=False), analytics=_analytics(), portfolio_risk=_risk()
    )
    assert result.approved is False
    assert "IV_REGIME_FAILED" in result.reasons


def test_expected_move_failed_refused():
    result = integrate_strategy_evaluation(
        gates=_gates(move=False), analytics=_analytics(), portfolio_risk=_risk()
    )
    assert result.approved is False
    assert "EXPECTED_MOVE_FAILED" in result.reasons


def test_liquidity_failed_refused():
    result = integrate_strategy_evaluation(
        gates=_gates(liquidity=False), analytics=_analytics(), portfolio_risk=_risk()
    )
    assert result.approved is False
    assert "LIQUIDITY_FAILED" in result.reasons


def test_analytics_invalid_refused():
    result = integrate_strategy_evaluation(
        gates=_gates(), analytics=_analytics(valid=False), portfolio_risk=_risk()
    )
    assert result.approved is False
    assert "ANALYTICS_INVALID" in result.reasons


def test_portfolio_risk_not_approved_refused():
    result = integrate_strategy_evaluation(
        gates=_gates(), analytics=_analytics(), portfolio_risk=_risk(approved=False)
    )
    assert result.approved is False
    assert "PORTFOLIO_RISK_NOT_APPROVED" in result.reasons


def test_invalid_inputs_refused():
    result = integrate_strategy_evaluation(
        gates="not_gates", analytics=_analytics(), portfolio_risk=_risk()
    )
    assert result.approved is False
    assert "INVALID_INPUTS" in result.reasons
