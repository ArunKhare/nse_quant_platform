"""Tests for the native iron-condor decision-loop integration."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    initialize_audited_decision_reconciliation_silver,
)
from nse_quant.data_platform.audited_decision_run_silver import (
    initialize_audited_decision_run_silver,
)
from nse_quant.data_platform.native_authoritative_identity_time_boundary import (
    VERSION as BOUNDARY_VERSION,
)
from nse_quant.data_platform.native_iron_condor_decision_loop_integration import (
    run_native_iron_condor_decision_loop,
)
from nse_quant.data_platform.native_iron_condor_decision_run_orchestrator import (
    NativeDecisionRunRequest,
)
from nse_quant.data_platform.native_iron_condor_portfolio_risk_decision import (
    NativePortfolioRiskDecisionInputBundle,
    PortfolioRiskSettings,
)
from nse_quant.data_platform.native_iron_condor_strategy_decision import (
    NativeStrategyDecisionInputBundle,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import (
    DEFINITION_SHA256,
    STAGES,
    STRATEGY,
    VERSION,
)


def _coverage() -> dict[str, object]:
    covered = ["market_session"]
    return {
        "version": VERSION,
        "strategy": STRATEGY,
        "definition_sha256": DEFINITION_SHA256,
        "stages": STAGES,
        "covered": covered,
        "unlinked": [],
        "missing": [
            requirement_id
            for requirement_id, _source, _need in __import__(
                "nse_quant.data_platform.native_strategy_requirements",
                fromlist=["REQUIREMENTS"],
            ).REQUIREMENTS
            if requirement_id not in covered
        ],
        "evidence_refs": {
            "market_session": (
                "silver://market_session?revision_id="
                + "a" * 64
                + "&recording_fingerprint="
                + "b" * 64
                + "&row_count=1"
            )
        },
        "revision_id": "a" * 64,
        "recording_fingerprint": "b" * 64,
        "complete": False,
    }


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
        run_id="loop-run-1",
        actor_id="researcher",
        code_revision="a" * 40,
        strategy_bundle=_strategy_bundle(),
        portfolio_risk_bundle=_risk_bundle(),
    )


def _boundary() -> dict[str, object]:
    return {
        "version": BOUNDARY_VERSION,
        "strategy": STRATEGY,
        "run_id": "loop-run-1",
        "requirement": "authoritative_identity_and_time",
        "identity": {
            "canonical_underlying": "NIFTY",
            "source": "exchange_master",
            "revision_id": "a" * 64,
            "recording_fingerprint": "b" * 64,
        },
        "derivative": {
            "binding": "canonical_underlying_to_derivative",
            "revision_id": "c" * 64,
            "recording_fingerprint": "d" * 64,
        },
        "authorized_revocation": {
            "authorized": True,
            "revision_id": "e" * 64,
            "recording_fingerprint": "f" * 64,
        },
        "point_in_time_decision": False,
        "auto_coverable": False,
        "decision_eligibility_asserted": False,
    }


@pytest.fixture()
def targets(tmp_path: Path):
    decision_path = tmp_path / "native-decision-run.duckdb"
    reconciliation_path = tmp_path / "native-reconciliation.duckdb"
    with (
        duckdb.connect(str(decision_path)) as decision_target,
        duckdb.connect(str(reconciliation_path)) as reconciliation_target,
    ):
        initialize_audited_decision_run_silver(decision_target)
        initialize_audited_decision_reconciliation_silver(reconciliation_target)
        yield decision_target, reconciliation_target


def test_runs_reconciles_persists_and_replays(targets) -> None:
    decision_target, reconciliation_target = targets
    result = run_native_iron_condor_decision_loop(
        decision_target,
        reconciliation_target,
        request=_request(),
        coverage_report=_coverage(),
        authoritative_boundary=_boundary(),
    )
    assert result["decision_run"]["recording"]["stage_count"] == 2
    assert result["reconciliation"]["decision_eligibility_asserted"] is False
    assert result["replay"]["replayed"] is True
    assert result["decision_eligibility_asserted"] is False


def test_point_in_time_boundary_rejected(targets) -> None:
    decision_target, reconciliation_target = targets
    boundary = _boundary()
    boundary["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        run_native_iron_condor_decision_loop(
            decision_target,
            reconciliation_target,
            request=_request(),
            coverage_report=_coverage(),
            authoritative_boundary=boundary,
        )


def test_missing_coverage_rejected(targets) -> None:
    decision_target, reconciliation_target = targets
    with pytest.raises(Rejected, match="COVERAGE_REPORT_REQUIRED"):
        run_native_iron_condor_decision_loop(
            decision_target,
            reconciliation_target,
            request=_request(),
            coverage_report=None,
            authoritative_boundary=_boundary(),
        )
