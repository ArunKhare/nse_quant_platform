"""Tests for persisted audited decision-run reconciliation Silver."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    VERSION as RECONCILIATION_VERSION,
)
from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    initialize_audited_decision_reconciliation_silver,
    reconciliation_context,
    record_audited_decision_reconciliation,
    replay_audited_decision_reconciliation,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import STRATEGY, VERSION


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _reconciliation() -> dict[str, object]:
    return {
        "version": RECONCILIATION_VERSION,
        "strategy": STRATEGY,
        "run_id": "run-1",
        "coverage_revision_id": "a" * 64,
        "coverage_recording_fingerprint": "b" * 64,
        "coverage": {
            "version": VERSION,
            "revision_id": "a" * 64,
            "recording_fingerprint": "b" * 64,
            "covered": ["market_session"],
            "unlinked": [],
            "missing": [
                requirement_id
                for requirement_id, _source, _need in __import__(
                    "nse_quant.data_platform.native_strategy_requirements",
                    fromlist=["REQUIREMENTS"],
                ).REQUIREMENTS
                if requirement_id != "market_session"
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
            "complete": False,
        },
        "stages": [
            {
                "stage": "strategy",
                "replayed": True,
                "revision_id": "c" * 64,
                "recording_fingerprint": "d" * 64,
                "decision_eligibility_asserted": False,
            },
            {
                "stage": "portfolio_risk",
                "replayed": False,
                "reason": "STAGE_NOT_EXECUTED",
                "decision_eligibility_asserted": False,
            },
        ],
        "complete": False,
        "decision_eligibility_asserted": False,
    }


@pytest.fixture()
def target(tmp_path: Path):
    path = tmp_path / "audited-decision-reconciliation.duckdb"
    with duckdb.connect(str(path)) as connection:
        initialize_audited_decision_reconciliation_silver(connection)
        yield connection


def test_records_and_replays_reconciliation(target) -> None:
    reconciliation = _reconciliation()
    result = record_audited_decision_reconciliation(
        target,
        reconciliation=reconciliation,
        expected_context_sha256=reconciliation_context(reconciliation),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    assert result["decision_eligibility_asserted"] is False

    replay = replay_audited_decision_reconciliation(
        target,
        run_id="run-1",
        expected_revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    assert replay["replayed"] is True
    assert replay["reconciliation"] == reconciliation
    assert replay["decision_eligibility_asserted"] is False


def test_duplicate_reconciliation_rejected(target) -> None:
    reconciliation = _reconciliation()
    record_audited_decision_reconciliation(
        target,
        reconciliation=reconciliation,
        expected_context_sha256=reconciliation_context(reconciliation),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    with pytest.raises(Rejected, match="RECONCILIATION_FIRST_WRITE_OR_ORPHAN_OBLIGATION"):
        record_audited_decision_reconciliation(
            target,
            reconciliation=reconciliation,
            expected_context_sha256=reconciliation_context(reconciliation),
            actor_id="researcher",
            code_revision="a" * 40,
        )


def test_complete_reconciliation_rejected(target) -> None:
    reconciliation = _reconciliation()
    reconciliation["complete"] = True
    with pytest.raises(Rejected, match="RECONCILIATION_COMPLETION_NOT_ASSERTABLE"):
        reconciliation_context(reconciliation)


def test_changed_context_rejected(target) -> None:
    reconciliation = _reconciliation()
    with pytest.raises(Rejected, match="REVIEWED_RECONCILIATION_CONTEXT_CHANGED"):
        record_audited_decision_reconciliation(
            target,
            reconciliation=reconciliation,
            expected_context_sha256="a" * 64,
            actor_id="researcher",
            code_revision="a" * 40,
        )
