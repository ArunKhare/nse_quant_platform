"""Tests for native iron-condor portfolio-risk decision evaluation."""

from __future__ import annotations

import pytest

from nse_quant.data_platform.native_iron_condor_portfolio_risk_decision import (
    NativePortfolioRiskDecisionInputBundle,
    PortfolioRiskSettings,
    evaluate_native_portfolio_risk_decision,
    native_portfolio_risk_decision_fingerprint,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _bundle() -> NativePortfolioRiskDecisionInputBundle:
    return NativePortfolioRiskDecisionInputBundle(
        coverage_revision_id="a" * 64,
        coverage_recording_fingerprint="b" * 64,
        evidence_refs={
            "market_session": (
                "silver://market_session?revision_id="
                + "c" * 64
                + "&recording_fingerprint="
                + "d" * 64
                + "&row_count=1"
            )
        },
        strategy_outcome={
            "decision_type": "NATIVE_STRATEGY_DECISION",
            "action": "monitor",
            "decision_eligibility_asserted": False,
        },
        proposal={"underlying": "NIFTY", "notional": 100000.0},
        open_positions=[],
        settings=PortfolioRiskSettings(),
    )


def test_evaluates_approved_risk_decision() -> None:
    bundle = _bundle()
    outcome = evaluate_native_portfolio_risk_decision(bundle)
    assert outcome["decision_type"] == "NATIVE_PORTFOLIO_RISK_DECISION"
    assert outcome["action"] == "approve"
    assert outcome["decision_eligibility_asserted"] is False

    fingerprint = native_portfolio_risk_decision_fingerprint(
        inputs={
            "coverage_revision_id": bundle.coverage_revision_id,
            "coverage_recording_fingerprint": bundle.coverage_recording_fingerprint,
            "evidence_refs": bundle.evidence_refs,
            "strategy_outcome": bundle.strategy_outcome,
            "proposal": bundle.proposal,
            "open_positions": bundle.open_positions,
            "settings": {
                "max_open_positions": bundle.settings.max_open_positions,
                "max_notional_exposure": bundle.settings.max_notional_exposure,
                "max_concentration_pct": bundle.settings.max_concentration_pct,
            },
        },
        outcome=outcome,
    )
    assert len(fingerprint) == 64


def test_blocks_excessive_notional() -> None:
    bundle = _bundle()
    object.__setattr__(
        bundle,
        "proposal",
        {"underlying": "NIFTY", "notional": 2_000_000.0},
    )
    outcome = evaluate_native_portfolio_risk_decision(bundle)
    assert outcome["action"] == "block"
    assert "max_notional_exposure_exceeded" in outcome["reasons"]
    assert outcome["decision_eligibility_asserted"] is False


def test_point_in_time_strategy_rejected() -> None:
    bundle = _bundle()
    object.__setattr__(
        bundle,
        "strategy_outcome",
        {
            "decision_type": "POINT_IN_TIME_DECISION",
            "action": "monitor",
            "decision_eligibility_asserted": False,
        },
    )
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION_REJECTED"):
        evaluate_native_portfolio_risk_decision(bundle)


def test_invalid_strategy_outcome_rejected() -> None:
    bundle = _bundle()
    object.__setattr__(
        bundle,
        "strategy_outcome",
        {
            "decision_type": "NATIVE_STRATEGY_DECISION",
            "action": "execute",
            "decision_eligibility_asserted": False,
        },
    )
    with pytest.raises(Rejected, match="UNSUPPORTED_STRATEGY_ACTION"):
        evaluate_native_portfolio_risk_decision(bundle)


def test_identity_requirement_rejected() -> None:
    bundle = _bundle()
    evidence = dict(bundle.evidence_refs)
    evidence["authoritative_identity_and_time"] = "silver://identity"
    object.__setattr__(bundle, "evidence_refs", evidence)
    with pytest.raises(Rejected, match="AUTHORITATIVE_IDENTITY_NOT_AUTO_COVERABLE"):
        evaluate_native_portfolio_risk_decision(bundle)
