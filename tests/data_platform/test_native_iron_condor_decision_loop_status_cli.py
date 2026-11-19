"""Tests for the native iron-condor decision-loop status/query CLI."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    initialize_audited_decision_reconciliation_silver,
    reconciliation_context,
)
from nse_quant.data_platform.native_authoritative_identity_time_boundary import (
    VERSION as BOUNDARY_VERSION,
)
from nse_quant.data_platform.native_iron_condor_decision_loop_status_cli import (
    main,
)
from nse_quant.data_platform.native_iron_condor_decision_reconciliation_boundary import (
    build_reconciliation_with_authoritative_boundary,
    record_reconciliation_with_authoritative_boundary,
)
from nse_quant.data_platform.native_strategy_requirements import STRATEGY


def _reconciliation() -> dict[str, object]:
    return {
        "version": "native-audited-decision-reconciliation-silver-recording@1",
        "strategy": STRATEGY,
        "run_id": "status-run-1",
        "coverage_revision_id": "a" * 64,
        "coverage_recording_fingerprint": "b" * 64,
        "coverage": {
            "revision_id": "a" * 64,
            "recording_fingerprint": "b" * 64,
            "covered": ["market_session"],
            "unlinked": [],
            "missing": [],
            "evidence_refs": {},
            "complete": False,
        },
        "stages": [
            {
                "stage": "strategy",
                "replayed": True,
                "revision_id": "c" * 64,
                "recording_fingerprint": "d" * 64,
                "decision_eligibility_asserted": False,
            }
        ],
        "complete": False,
        "decision_eligibility_asserted": False,
    }


def _boundary() -> dict[str, object]:
    return {
        "version": BOUNDARY_VERSION,
        "strategy": STRATEGY,
        "run_id": "status-run-1",
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
def prepared(tmp_path: Path):
    database_path = tmp_path / "native-reconciliation.duckdb"
    with duckdb.connect(str(database_path)) as target:
        initialize_audited_decision_reconciliation_silver(target)
        reconciliation = _reconciliation()
        boundary = _boundary()
        extended = build_reconciliation_with_authoritative_boundary(
            reconciliation,
            boundary,
        )
        context = reconciliation_context(extended)
        recorded = record_reconciliation_with_authoritative_boundary(
            target,
            reconciliation=reconciliation,
            boundary=boundary,
            expected_context_sha256=context,
            actor_id="researcher",
            code_revision="a" * 40,
        )
    return (
        database_path,
        recorded["revision_id"],
        recorded["recording_fingerprint"],
    )


def test_status_cli_replays_reconciliation(prepared, capsys) -> None:
    database_path, revision_id, fingerprint = prepared
    exit_code = main(
        [
            "--reconciliation-database",
            str(database_path),
            "--run-id",
            "status-run-1",
            "--revision-id",
            revision_id,
            "--recording-fingerprint",
            fingerprint,
        ]
    )
    assert exit_code == 0, capsys.readouterr().out
    output = json.loads(capsys.readouterr().out)
    assert output["replayed"] is True
    assert output["authoritative_boundary"]["run_id"] == "status-run-1"
    assert output["decision_eligibility_asserted"] is False


def test_status_cli_rejects_wrong_revision(prepared, capsys) -> None:
    database_path, _revision_id, fingerprint = prepared
    exit_code = main(
        [
            "--reconciliation-database",
            str(database_path),
            "--run-id",
            "status-run-1",
            "--revision-id",
            "0" * 64,
            "--recording-fingerprint",
            fingerprint,
        ]
    )
    assert exit_code == 2
    output = json.loads(capsys.readouterr().out)
    assert output["rejected"] == "RECONCILIATION_REVISION_MISMATCH"


def test_status_cli_rejects_missing_database(capsys) -> None:
    exit_code = main(
        [
            "--reconciliation-database",
            "missing.duckdb",
            "--run-id",
            "status-run-1",
            "--revision-id",
            "a" * 64,
            "--recording-fingerprint",
            "b" * 64,
        ]
    )
    assert exit_code == 2
    output = json.loads(capsys.readouterr().out)
    assert output["rejected"] == "RECONCILIATION_DATABASE_REQUIRED"
