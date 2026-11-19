"""Tests for availability and economic-validity evidence Silver."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from nse_quant.data_platform.native_availability_economic_validity_evidence import (
    evidence_context,
    initialize_availability_economic_evidence_silver,
    record_availability_economic_evidence,
    replay_availability_economic_evidence,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import STRATEGY


def _evidence() -> dict[str, object]:
    return {
        "version": "native-availability-economic-validity-evidence-silver@1",
        "strategy": STRATEGY,
        "run_id": "availability-run-1",
        "availability": {
            "available": True,
            "source": "exchange_master",
            "revision_id": "a" * 64,
            "recording_fingerprint": "b" * 64,
        },
        "economic_validity": {
            "valid": True,
            "source": "exchange_master",
            "revision_id": "c" * 64,
            "recording_fingerprint": "d" * 64,
        },
        "knowledge_cutoff": "2026-11-17T00:00:00+00:00",
        "economic_at": "2026-11-17T00:00:00+00:00",
        "point_in_time_decision": False,
        "auto_coverable": False,
        "decision_eligibility_asserted": False,
    }


@pytest.fixture()
def target(tmp_path: Path):
    path = tmp_path / "availability-economic-evidence.duckdb"
    with duckdb.connect(str(path)) as connection:
        initialize_availability_economic_evidence_silver(connection)
        yield connection


def test_records_and_replays_availability_economic_evidence(target) -> None:
    evidence = _evidence()
    result = record_availability_economic_evidence(
        target,
        evidence=evidence,
        expected_context_sha256=evidence_context(evidence),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    assert result["decision_eligibility_asserted"] is False
    replay = replay_availability_economic_evidence(
        target,
        run_id="availability-run-1",
        expected_revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    assert replay["replayed"] is True
    assert replay["evidence"] == evidence


def test_duplicate_evidence_rejected(target) -> None:
    evidence = _evidence()
    record_availability_economic_evidence(
        target,
        evidence=evidence,
        expected_context_sha256=evidence_context(evidence),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    with pytest.raises(Rejected, match="AVAILABILITY_ECONOMIC_FIRST_WRITE_OR_ORPHAN_OBLIGATION"):
        record_availability_economic_evidence(
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


def test_missing_economic_at_rejected(target) -> None:
    evidence = _evidence()
    del evidence["economic_at"]
    with pytest.raises(Rejected, match="ECONOMIC_AT_REQUIRED"):
        evidence_context(evidence)
