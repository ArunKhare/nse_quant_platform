"""Tests for native portfolio-risk evaluation."""

from __future__ import annotations

from nse_quant.risk.native_portfolio_risk import (
    PortfolioRiskSettings,
    evaluate_portfolio_risk,
)


def _settings():
    return PortfolioRiskSettings(
        max_open_positions=3,
        max_notional_exposure=100000.0,
        max_concentration_pct=50.0,
    )


def test_valid_proposal_approved():
    proposal = dict(underlying="NIFTY", notional=10000.0)
    result = evaluate_portfolio_risk(proposal=proposal, open_positions=[], settings=_settings())
    assert result.approved is True
    assert result.reasons == []
    assert len(result.checks) == 3


def test_max_open_positions_exceeded():
    proposal = dict(underlying="NIFTY", notional=10000.0)
    open_positions = [dict(underlying="NIFTY", notional=1000.0) for _ in range(3)]
    result = evaluate_portfolio_risk(
        proposal=proposal, open_positions=open_positions, settings=_settings()
    )
    assert result.approved is False
    assert "max_open_positions_exceeded" in result.reasons


def test_max_notional_exceeded():
    proposal = dict(underlying="NIFTY", notional=60000.0)
    open_positions = [dict(underlying="NIFTY", notional=50000.0)]
    result = evaluate_portfolio_risk(
        proposal=proposal, open_positions=open_positions, settings=_settings()
    )
    assert result.approved is False
    assert "max_notional_exposure_exceeded" in result.reasons


def test_concentration_exceeded():
    proposal = dict(underlying="NIFTY", notional=60000.0)
    open_positions = [dict(underlying="NIFTY", notional=40000.0)]
    result = evaluate_portfolio_risk(
        proposal=proposal, open_positions=open_positions, settings=_settings()
    )
    assert result.approved is False
    assert "max_concentration_pct_exceeded" in result.reasons


def test_invalid_proposal_refused():
    result = evaluate_portfolio_risk(
        proposal=dict(underlying="NIFTY"),
        open_positions=[],
        settings=_settings(),
    )
    assert result.approved is False
    assert "invalid_proposal" in result.reasons


def test_invalid_notional_refused():
    result = evaluate_portfolio_risk(
        proposal=dict(underlying="NIFTY", notional=-1.0),
        open_positions=[],
        settings=_settings(),
    )
    assert result.approved is False
    assert "invalid_notional" in result.reasons
