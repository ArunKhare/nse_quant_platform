"""Tests for composite audited native decision-run recording and replay."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from nse_quant.data_platform.audited_decision_run_composite import (
    CompositeDecisionRunRequest,
    CompositeDecisionStage,
    composite_context,
    record_composite_audited_decision_run,
    replay_composite_audited_decision_run,
)
from nse_quant.data_platform.audited_decision_run_silver import (
    initialize_audited_decision_run_silver,
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


def _stage(stage: str) -> CompositeDecisionStage:
    inputs = {"symbol": "RELIANCE"} if stage == "strategy" else {"portfolio": "default"}
    outcome = {"approved": False}
    return CompositeDecisionStage(
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
    )


def _request(stages: tuple[CompositeDecisionStage, ...]) -> CompositeDecisionRunRequest:
    return CompositeDecisionRunRequest(
        run_id="composite-run-1",
        coverage_revision_id="b" * 64,
        coverage_recording_fingerprint="c" * 64,
        stages=stages,
    )


@pytest.fixture()
def target(tmp_path: Path):
    path = tmp_path / "composite-audited-decision-run-silver.duckdb"
    with duckdb.connect(str(path)) as connection:
        initialize_audited_decision_run_silver(connection)
        yield connection


def test_records_and_replays_both_stages(target) -> None:
    request = _request((_stage("strategy"), _stage("portfolio_risk")))
    result = record_composite_audited_decision_run(
        target,
        request=request,
        expected_context_sha256=composite_context(request),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    assert result["stage_count"] == 2
    assert result["decision_eligibility_asserted"] is False

    revisions = {item["stage"]: item["revision_id"] for item in result["stages"]}
    fingerprints = {item["stage"]: item["recording_fingerprint"] for item in result["stages"]}
    replay = replay_composite_audited_decision_run(
        target,
        run_id="composite-run-1",
        stages=("strategy", "portfolio_risk"),
        expected_stage_revisions=revisions,
        expected_stage_recording_fingerprints=fingerprints,
    )
    assert all(item["replayed"] is True for item in replay["stages"])
    assert replay["decision_eligibility_asserted"] is False


def test_records_and_replays_only_strategy(target) -> None:
    request = _request((_stage("strategy"),))
    result = record_composite_audited_decision_run(
        target,
        request=request,
        expected_context_sha256=composite_context(request),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    revisions = {item["stage"]: item["revision_id"] for item in result["stages"]}
    fingerprints = {item["stage"]: item["recording_fingerprint"] for item in result["stages"]}
    replay = replay_composite_audited_decision_run(
        target,
        run_id="composite-run-1",
        stages=("strategy", "portfolio_risk"),
        expected_stage_revisions=revisions,
        expected_stage_recording_fingerprints=fingerprints,
    )
    assert replay["stages"][0]["replayed"] is True
    assert replay["stages"][1] == {
        "stage": "portfolio_risk",
        "replayed": False,
        "reason": "STAGE_NOT_EXECUTED",
        "decision_eligibility_asserted": False,
    }


def test_point_in_time_decision_rejected(target) -> None:
    strategy = _stage("strategy")
    strategy.outcome["decision_type"] = "POINT_IN_TIME_DECISION"
    request = _request((strategy,))
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION_REJECTED"):
        record_composite_audited_decision_run(
            target,
            request=request,
            expected_context_sha256=composite_context(request),
            actor_id="researcher",
            code_revision="a" * 40,
        )


def test_duplicate_stage_rejected(target) -> None:
    request = _request((_stage("strategy"), _stage("strategy")))
    with pytest.raises(Rejected, match="DUPLICATE_DECISION_STAGE"):
        composite_context(request)


def test_changed_context_rejected(target) -> None:
    request = _request((_stage("strategy"),))
    with pytest.raises(Rejected, match="REVIEWED_COMPOSITE_DECISION_RUN_CONTEXT_CHANGED"):
        record_composite_audited_decision_run(
            target,
            request=request,
            expected_context_sha256="a" * 64,
            actor_id="researcher",
            code_revision="a" * 40,
        )
