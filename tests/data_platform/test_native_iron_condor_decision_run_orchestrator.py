"""Tests for the native iron-condor decision-run orchestrator."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from nse_quant.data_platform.audited_decision_run_silver import (
    initialize_audited_decision_run_silver,
)
from nse_quant.data_platform.native_iron_condor_decision_run_orchestrator import (
    NativeDecisionRunRequest,
    run_native_iron_condor_decision,
)
from nse_quant.data_platform.native_iron_condor_portfolio_risk_decision import (
    NativePortfolioRiskDecisionInputBundle,
    PortfolioRiskSettings,
)
from nse_quant.data_platform.native_iron_condor_strategy_decision import (
    NativeStrategyDecisionInputBundle,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _strategy_bundle() -> NativeStrategyDecisionInputBundle:
    evidence = {
        requirement: (f"silver://{requirement}?revision_id={'a' * 64}&recording_fingerprint={'b' * 64}&row_count=1")
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


def _risk_bundle() -> NativePortfolioRiskDecisionInputBundle:
    return NativePortfolioRiskDecisionInputBundle(
        coverage_revision_id="a" * 64,
        coverage_recording_fingerprint="b" * 64,
        evidence_refs={
            "market_session": (
                "silver://market_session?revision_id="
                + "a" * 64
                + "&recording_fingerprint="
                + "b" * 64
                + "&row_count=1"
            )
        },
        strategy_outcome={},
        proposal={"underlying": "NIFTY", "notional": 100000.0},
        open_positions=[],
        settings=PortfolioRiskSettings(),
    )


def _request() -> NativeDecisionRunRequest:
    return NativeDecisionRunRequest(
        run_id="native-run-1",
        actor_id="researcher",
        code_revision="a" * 40,
        strategy_bundle=_strategy_bundle(),
        portfolio_risk_bundle=_risk_bundle(),
    )


@pytest.fixture()
def target(tmp_path: Path):
    path = tmp_path / "native-decision-run.duckdb"
    with duckdb.connect(str(path)) as connection:
        initialize_audited_decision_run_silver(connection)
        yield connection


def test_runs_records_and_replays_both_stages(target) -> None:
    result = run_native_iron_condor_decision(target, request=_request())
    assert result["strategy_outcome"]["decision_type"] == "NATIVE_STRATEGY_DECISION"
    assert result["portfolio_risk_outcome"]["decision_type"] == "NATIVE_PORTFOLIO_RISK_DECISION"
    assert result["recording"]["stage_count"] == 2
    assert all(item["replayed"] for item in result["replay"]["stages"])
    assert result["decision_eligibility_asserted"] is False


def test_duplicate_run_rejected(target) -> None:
    run_native_iron_condor_decision(target, request=_request())
    with pytest.raises(Rejected, match="AUDITED_DECISION_RUN_FIRST_WRITE_OR_ORPHAN_OBLIGATION"):
        run_native_iron_condor_decision(target, request=_request())


def test_never_produces_point_in_time_decision(target) -> None:
    result = run_native_iron_condor_decision(target, request=_request())

    assert result["strategy_outcome"]["decision_type"] == "NATIVE_STRATEGY_DECISION"
    assert result["portfolio_risk_outcome"]["decision_type"] == "NATIVE_PORTFOLIO_RISK_DECISION"
    assert result["strategy_outcome"]["decision_type"] != "POINT_IN_TIME_DECISION"
    assert result["portfolio_risk_outcome"]["decision_type"] != "POINT_IN_TIME_DECISION"
    assert result["decision_eligibility_asserted"] is False
