"""Tests for persisted evidence-linked audited decision-run Silver recording."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from nse_quant.data_platform.audited_decision_run_silver import (
    AuditedDecisionRunRequest,
    audited_decision_run_context,
    initialize_audited_decision_run_silver,
    record_audited_decision_run,
    replay_audited_decision_run,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


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


def _request(stage: str = "strategy") -> AuditedDecisionRunRequest:
    inputs = {"symbol": "RELIANCE"} if stage == "strategy" else {"portfolio": "default"}
    outcome = {"approved": False}
    return AuditedDecisionRunRequest(
        run_id="run-1",
        stage=stage,
        decision_fingerprint=_sha([stage, inputs, outcome]),
        inputs=inputs,
        outcome=outcome,
        evidence_refs={
            "market_session": (
                "silver://market_session?revision_id="
                + "b" * 64
                + "&recording_fingerprint="
                + "c" * 64
                + "&row_count=1"
            )
        },
        coverage_revision_id="b" * 64,
        coverage_recording_fingerprint="c" * 64,
    )


def _context(request: AuditedDecisionRunRequest) -> str:
    return audited_decision_run_context(request)


@pytest.fixture()
def target(tmp_path: Path):
    path = tmp_path / "audited-decision-run-silver.duckdb"
    with duckdb.connect(str(path)) as connection:
        initialize_audited_decision_run_silver(connection)
        yield connection


def test_records_and_replays_strategy_stage(target) -> None:
    expected_decision_fingerprint = _sha(
        [
            "strategy",
            {"symbol": "RELIANCE"},
            {"approved": False},
        ]
    )
    request = _request()
    result = record_audited_decision_run(
        target,
        request=request,
        expected_context_sha256=_context(request),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    assert result["decision_eligibility_asserted"] is False
    assert result["stage_count"] == 1

    replay = replay_audited_decision_run(
        target,
        run_id="run-1",
        stage="strategy",
        expected_revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    assert replay["replayed"] is True
    assert replay["decision_fingerprint"] == expected_decision_fingerprint
    assert replay["decision_eligibility_asserted"] is False


def test_point_in_time_decision_rejected(target) -> None:
    request = _request()
    request.outcome["decision_type"] = "POINT_IN_TIME_DECISION"
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION_REJECTED"):
        record_audited_decision_run(
            target,
            request=request,
            expected_context_sha256=_context(request),
            actor_id="researcher",
            code_revision="a" * 40,
        )


def test_duplicate_run_stage_rejected(target) -> None:
    request = _request()
    record_audited_decision_run(
        target,
        request=request,
        expected_context_sha256=_context(request),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    with pytest.raises(Rejected, match="AUDITED_DECISION_RUN_FIRST_WRITE_OR_ORPHAN_OBLIGATION"):
        record_audited_decision_run(
            target,
            request=request,
            expected_context_sha256=_context(request),
            actor_id="researcher",
            code_revision="a" * 40,
        )


def test_unrecorded_stage_not_replayed(target) -> None:
    request = _request()
    result = record_audited_decision_run(
        target,
        request=request,
        expected_context_sha256=_context(request),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    replay = replay_audited_decision_run(
        target,
        run_id="run-1",
        stage="portfolio_risk",
        expected_revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    assert replay == {
        "run_id": "run-1",
        "stage": "portfolio_risk",
        "replayed": False,
        "reason": "STAGE_NOT_EXECUTED",
        "decision_eligibility_asserted": False,
    }
