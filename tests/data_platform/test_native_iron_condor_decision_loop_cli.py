"""Tests for the native iron-condor decision-loop CLI."""

from __future__ import annotations

import json
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
from nse_quant.data_platform.native_iron_condor_decision_loop_cli import (
    main,
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
        run_id="cli-run-1",
        actor_id="researcher",
        code_revision="a" * 40,
        strategy_bundle=_strategy_bundle(),
        portfolio_risk_bundle=_risk_bundle(),
    )


def _boundary() -> dict[str, object]:
    return {
        "version": BOUNDARY_VERSION,
        "strategy": STRATEGY,
        "run_id": "cli-run-1",
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


def _json_default(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if hasattr(value, "__dict__"):
        return vars(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


@pytest.fixture()
def prepared(tmp_path: Path):
    decision_path = tmp_path / "native-decision-run.duckdb"
    reconciliation_path = tmp_path / "native-reconciliation.duckdb"
    with (
        duckdb.connect(str(decision_path)) as decision_target,
        duckdb.connect(str(reconciliation_path)) as reconciliation_target,
    ):
        initialize_audited_decision_run_silver(decision_target)
        initialize_audited_decision_reconciliation_silver(reconciliation_target)
    request_path = tmp_path / "request.json"
    coverage_path = tmp_path / "coverage.json"
    boundary_path = tmp_path / "boundary.json"
    request_path.write_text(
        json.dumps(
            {
                "run_id": "cli-run-1",
                "actor_id": "researcher",
                "code_revision": "a" * 40,
                "strategy_bundle": _strategy_bundle(),
                "portfolio_risk_bundle": _risk_bundle(),
            },
            default=_json_default,
        ),
        encoding="utf-8",
    )
    coverage_path.write_text(json.dumps(_coverage()), encoding="utf-8")
    boundary_path.write_text(json.dumps(_boundary()), encoding="utf-8")
    return decision_path, reconciliation_path, request_path, coverage_path, boundary_path


def test_cli_runs_and_replays(prepared, capsys) -> None:
    decision_path, reconciliation_path, request_path, coverage_path, boundary_path = prepared
    exit_code = main(
        [
            "--decision-database",
            str(decision_path),
            "--reconciliation-database",
            str(reconciliation_path),
            "--request-json",
            str(request_path),
            "--coverage-json",
            str(coverage_path),
            "--boundary-json",
            str(boundary_path),
        ]
    )
    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["decision_run"]["recording"]["stage_count"] == 2
    assert output["replay"]["replayed"] is True
    assert output["decision_eligibility_asserted"] is False
    assert exit_code == 0, capsys.readouterr().out


def test_cli_rejects_point_in_time_boundary(prepared, capsys) -> None:
    decision_path, reconciliation_path, request_path, coverage_path, boundary_path = prepared
    boundary = _boundary()
    boundary["point_in_time_decision"] = True
    boundary_path.write_text(json.dumps(boundary), encoding="utf-8")
    exit_code = main(
        [
            "--decision-database",
            str(decision_path),
            "--reconciliation-database",
            str(reconciliation_path),
            "--request-json",
            str(request_path),
            "--coverage-json",
            str(coverage_path),
            "--boundary-json",
            str(boundary_path),
        ]
    )
    assert exit_code == 2
    output = json.loads(capsys.readouterr().out)
    assert output["rejected"] == "POINT_IN_TIME_DECISION"
    assert exit_code == 0, capsys.readouterr().out


def test_cli_missing_coverage_rejected(prepared, capsys) -> None:
    decision_path, reconciliation_path, request_path, _coverage_path, boundary_path = prepared
    exit_code = main(
        [
            "--decision-database",
            str(decision_path),
            "--reconciliation-database",
            str(reconciliation_path),
            "--request-json",
            str(request_path),
            "--coverage-json",
            str(Path("missing.json")),
            "--boundary-json",
            str(boundary_path),
        ]
    )
    assert exit_code == 2
    output = json.loads(capsys.readouterr().out)
    assert output["rejected"] == "COVERAGE_FILE_REQUIRED"
    assert exit_code == 0, capsys.readouterr().out
