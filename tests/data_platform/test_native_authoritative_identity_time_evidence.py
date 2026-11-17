"""Tests for authoritative identity/time evidence Silver."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from nse_quant.data_platform.native_authoritative_identity_time_evidence import (
    evidence_context,
    initialize_identity_time_evidence_silver,
    record_identity_time_evidence,
    replay_identity_time_evidence,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import STRATEGY


def _evidence() -> dict[str, object]:
    return {
        "version": "native-authoritative-identity-time-evidence-silver@1",
        "strategy": STRATEGY,
        "run_id": "identity-run-1",
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
    path = tmp_path / "identity-time-evidence.duckdb"
    with duckdb.connect(str(path)) as connection:
        initialize_identity_time_evidence_silver(connection)
        yield connection


def test_records_and_replays_identity_time_evidence(target) -> None:
    evidence = _evidence()
    result = record_identity_time_evidence(
        target,
        evidence=evidence,
        expected_context_sha256=evidence_context(evidence),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    assert result["decision_eligibility_asserted"] is False
    replay = replay_identity_time_evidence(
        target,
        run_id="identity-run-1",
        expected_revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    assert replay["replayed"] is True
    assert replay["evidence"] == evidence


def test_duplicate_evidence_rejected(target) -> None:
    evidence = _evidence()
    record_identity_time_evidence(
        target,
        evidence=evidence,
        expected_context_sha256=evidence_context(evidence),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    with pytest.raises(Rejected, match="IDENTITY_TIME_EVIDENCE_FIRST_WRITE_OR_ORPHAN_OBLIGATION"):
        record_identity_time_evidence(
            target,
            evidence=evidence,
            expected_context_sha256=evidence_context(evidence),
            actor_id="researcher",
            code_revision="a" * 40,
        )


def test_point_in_time_evidence_rejected(target) -> None:
    evidence = _evidence()
    evidence["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        evidence_context(evidence)
