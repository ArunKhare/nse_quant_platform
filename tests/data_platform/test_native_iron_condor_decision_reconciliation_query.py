"""Tests for the bounded reconciliation query CLI."""

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
from nse_quant.data_platform.native_iron_condor_decision_reconciliation_boundary import (
    build_reconciliation_with_authoritative_boundary,
    record_reconciliation_with_authoritative_boundary,
)
from nse_quant.data_platform.native_iron_condor_decision_reconciliation_query import (
    main,
    query_native_iron_condor_decision_reconciliations,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import STRATEGY


def _reconciliation(run_id: str) -> dict[str, object]:
    return {
        "version": "native-audited-decision-reconciliation-silver-recording@1",
        "strategy": STRATEGY,
        "run_id": run_id,
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


def _boundary(run_id: str) -> dict[str, object]:
    return {
        "version": BOUNDARY_VERSION,
        "strategy": STRATEGY,
        "run_id": run_id,
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
def target(tmp_path: Path):
    path = tmp_path / "query-reconciliation.duckdb"
    connection = duckdb.connect(str(path))
    initialize_audited_decision_reconciliation_silver(connection)
    for run_id in ("query-run-1", "query-run-2"):
        reconciliation = _reconciliation(run_id)
        boundary = _boundary(run_id)
        extended = build_reconciliation_with_authoritative_boundary(
            reconciliation,
            boundary,
        )
        context = reconciliation_context(extended)
        record_reconciliation_with_authoritative_boundary(
            connection,
            reconciliation=reconciliation,
            boundary=boundary,
            expected_context_sha256=context,
            actor_id="researcher",
            code_revision="a" * 40,
        )
    yield connection, path
    connection.close()


def test_queries_bounded_summaries(target) -> None:
    connection, _path = target
    summaries = query_native_iron_condor_decision_reconciliations(
        connection,
        limit=2,
    )
    assert len(summaries) == 2
    assert all(item["decision_eligibility_asserted"] is False for item in summaries)
    assert all(item["authoritative_boundary_present"] is True for item in summaries)


def test_rejects_invalid_limit(target) -> None:
    connection, _path = target
    with pytest.raises(Rejected, match="RECONCILIATION_QUERY_LIMIT_INVALID"):
        query_native_iron_condor_decision_reconciliations(
            connection,
            limit=0,
        )


def test_cli_queries_summaries(target, capsys) -> None:
    _connection, path = target
    exit_code = main(
        [
            "--reconciliation-database",
            str(path),
            "--limit",
            "2",
        ]
    )
    assert exit_code == 0, capsys.readouterr().out
    summaries = json.loads(capsys.readouterr().out)
    assert len(summaries) == 2
    assert all(item["decision_eligibility_asserted"] is False for item in summaries)


def test_cli_rejects_missing_database(capsys) -> None:
    exit_code = main(
        [
            "--reconciliation-database",
            "missing.duckdb",
            "--limit",
            "2",
        ]
    )
    assert exit_code == 2
    output = json.loads(capsys.readouterr().out)
    assert output["rejected"] == "RECONCILIATION_DATABASE_REQUIRED"
