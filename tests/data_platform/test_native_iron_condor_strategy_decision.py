"""Tests for native iron-condor strategy decision evaluation."""

from __future__ import annotations

import pytest

from nse_quant.data_platform.native_iron_condor_strategy_decision import (
    NativeStrategyDecisionInputBundle,
    evaluate_native_strategy_decision,
    native_strategy_decision_fingerprint,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _bundle() -> NativeStrategyDecisionInputBundle:
    evidence = {
        requirement: f"silver://{requirement}?revision_id={'a' * 64}&recording_fingerprint={'b' * 64}&row_count=1"
        for requirement in (
            "market_session",
            "iv_rank_and_history",
            "iv_rv_spread",
            "expected_move",
            "effective_proposal_configuration",
            "chain_time_expiry_spot",
            "option_chain_and_contract_terms",
            "candidate_liquidity",
        )
    }
    return NativeStrategyDecisionInputBundle(
        coverage_revision_id="a" * 64,
        coverage_recording_fingerprint="b" * 64,
        evidence_refs=evidence,
        market_session={"is_market_open": True},
        iv_rank_and_history={"iv_rank": 40.0},
        iv_rv_spread={"iv_rv_spread": 2.0},
        expected_move={"expected_move_points": 100.0},
        effective_proposal_configuration={"minimum_credit": 1.0},
        chain_time_expiry_spot={"spot": 25000.0},
        option_chain_and_contract_terms={"contracts": []},
        candidate_liquidity={"tradable": True},
    )


def test_evaluates_monitor_decision() -> None:
    bundle = _bundle()
    outcome = evaluate_native_strategy_decision(bundle)
    assert outcome["action"] == "monitor"
    assert outcome["decision_type"] == "NATIVE_STRATEGY_DECISION"
    assert outcome["decision_eligibility_asserted"] is False
    fingerprint = native_strategy_decision_fingerprint(
        inputs={
            "coverage_revision_id": bundle.coverage_revision_id,
            "coverage_recording_fingerprint": bundle.coverage_recording_fingerprint,
            "evidence_refs": bundle.evidence_refs,
            "market_session": bundle.market_session,
            "iv_rank_and_history": bundle.iv_rank_and_history,
            "iv_rv_spread": bundle.iv_rv_spread,
            "expected_move": bundle.expected_move,
            "effective_proposal_configuration": bundle.effective_proposal_configuration,
            "chain_time_expiry_spot": bundle.chain_time_expiry_spot,
            "option_chain_and_contract_terms": bundle.option_chain_and_contract_terms,
            "candidate_liquidity": bundle.candidate_liquidity,
        },
        outcome=outcome,
    )
    assert len(fingerprint) == 64


def test_market_closed_rejected() -> None:
    bundle = _bundle()
    object.__setattr__(bundle, "market_session", {"is_market_open": False})
    with pytest.raises(Rejected, match="MARKET_SESSION_NOT_OPEN"):
        evaluate_native_strategy_decision(bundle)


def test_missing_coverage_rejected() -> None:
    bundle = _bundle()
    evidence = dict(bundle.evidence_refs)
    evidence.pop("candidate_liquidity")
    object.__setattr__(bundle, "evidence_refs", evidence)
    with pytest.raises(Rejected, match="REQUIRED_NATIVE_INPUT_COVERAGE_MISSING"):
        evaluate_native_strategy_decision(bundle)


def test_identity_requirement_rejected() -> None:
    bundle = _bundle()
    evidence = dict(bundle.evidence_refs)
    evidence["authoritative_identity_and_time"] = "silver://identity"
    object.__setattr__(bundle, "evidence_refs", evidence)
    with pytest.raises(Rejected, match="AUTHORITATIVE_IDENTITY_NOT_AUTO_COVERABLE"):
        evaluate_native_strategy_decision(bundle)


def test_point_in_time_decision_not_produced() -> None:
    outcome = evaluate_native_strategy_decision(_bundle())
    assert outcome["decision_type"] != "POINT_IN_TIME_DECISION"
