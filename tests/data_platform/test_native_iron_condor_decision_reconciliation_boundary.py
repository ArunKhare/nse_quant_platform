"""Tests for reconciliation with authoritative identity/time boundary."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    VERSION as BASE_RECONCILIATION_VERSION,
)
from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    reconciliation_context,
)
from nse_quant.data_platform.native_authoritative_identity_time_boundary import (
    VERSION as BOUNDARY_VERSION,
)
from nse_quant.data_platform.native_iron_condor_decision_reconciliation_boundary import (
    build_reconciliation_with_authoritative_boundary,
    record_reconciliation_with_authoritative_boundary,
    replay_reconciliation_with_authoritative_boundary,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import STRATEGY


def _reconciliation() -> dict[str, object]:
    return {
        "version": BASE_RECONCILIATION_VERSION,
        "strategy": STRATEGY,
        "run_id": "boundary-run-1",
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
        "run_id": "boundary-run-1",
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
    path = tmp_path / "boundary-reconciliation.duckdb"
    with duckdb.connect(str(path)) as connection:
        from nse_quant.data_platform.audited_decision_reconciliation_silver import (
            initialize_audited_decision_reconciliation_silver,
        )

        initialize_audited_decision_reconciliation_silver(connection)
        yield connection


def test_builds_and_persists_boundary_reconciliation(target) -> None:
    reconciliation = _reconciliation()
    boundary = _boundary()
    extended = build_reconciliation_with_authoritative_boundary(
        reconciliation,
        boundary,
    )
    context = reconciliation_context(extended)
    result = record_reconciliation_with_authoritative_boundary(
        target,
        reconciliation=reconciliation,
        boundary=boundary,
        expected_context_sha256=context,
        actor_id="researcher",
        code_revision="a" * 40,
    )
    assert result["decision_eligibility_asserted"] is False
    replay = replay_reconciliation_with_authoritative_boundary(
        target,
        run_id="boundary-run-1",
        expected_revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    assert replay["replayed"] is True
    assert replay["authoritative_boundary"] == boundary
    assert replay["decision_eligibility_asserted"] is False


def test_point_in_time_boundary_rejected(target) -> None:
    reconciliation = _reconciliation()
    boundary = _boundary()
    boundary["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        build_reconciliation_with_authoritative_boundary(
            reconciliation,
            boundary,
        )


def test_changed_context_rejected(target) -> None:
    reconciliation = _reconciliation()
    boundary = _boundary()
    with pytest.raises(Rejected, match="REVIEWED_RECONCILIATION_CONTEXT_CHANGED"):
        record_reconciliation_with_authoritative_boundary(
            target,
            reconciliation=reconciliation,
            boundary=boundary,
            expected_context_sha256="a" * 64,
            actor_id="researcher",
            code_revision="a" * 40,
        )
