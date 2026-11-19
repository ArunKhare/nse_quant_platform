"""Composite audited native decision-run recording and exact replay.

Composes persisted, evidence-linked strategy and portfolio-risk decision stages
into one immutable run. Replays only stages that actually ran. No eligibility,
live trading, healing, backfill, adoption, or execution authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from nse_quant.data_platform.audited_decision_run_silver import (
    AuditedDecisionRunRequest,
    audited_decision_run_context,
    record_audited_decision_run,
    replay_audited_decision_run,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

_SUPPORTED_STAGES = frozenset({"strategy", "portfolio_risk"})


@dataclass(frozen=True)
class CompositeDecisionStage:
    stage: str
    decision_fingerprint: str
    inputs: dict[str, Any]
    outcome: dict[str, Any]
    evidence_refs: dict[str, str]


@dataclass(frozen=True)
class CompositeDecisionRunRequest:
    run_id: str
    coverage_revision_id: str
    coverage_recording_fingerprint: str
    stages: tuple[CompositeDecisionStage, ...]


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _decision_fingerprint(stage: str, inputs: dict[str, Any], outcome: dict[str, Any]) -> str:
    return _sha(_canonical([stage, inputs, outcome]))


def _validate_stage(stage: CompositeDecisionStage) -> None:
    if type(stage) is not CompositeDecisionStage:
        raise Rejected("TYPED_DECISION_STAGE_REQUIRED")
    if stage.stage not in _SUPPORTED_STAGES:
        raise Rejected("UNSUPPORTED_STAGE")
    if type(stage.inputs) is not dict or type(stage.outcome) is not dict:
        raise Rejected("EXACT_DECISION_DOCUMENTS_REQUIRED")
    if type(stage.evidence_refs) is not dict or not stage.evidence_refs:
        raise Rejected("EXACT_EVIDENCE_REFS_REQUIRED")
    if any(
        type(key) is not str or not key or type(value) is not str or not value
        for key, value in stage.evidence_refs.items()
    ):
        raise Rejected("EXACT_EVIDENCE_REF_REQUIRED")
    if "authoritative_identity_and_time" in stage.evidence_refs:
        raise Rejected("AUTHORITATIVE_IDENTITY_NOT_AUTO_COVERABLE")
    if stage.outcome.get("decision_type") == "POINT_IN_TIME_DECISION":
        raise Rejected("POINT_IN_TIME_DECISION_REJECTED")
    if _decision_fingerprint(stage.stage, stage.inputs, stage.outcome) != stage.decision_fingerprint:
        raise Rejected("DECISION_FINGERPRINT_MISMATCH")


def _validate_request(request: CompositeDecisionRunRequest) -> None:
    if type(request) is not CompositeDecisionRunRequest:
        raise Rejected("TYPED_COMPOSITE_DECISION_RUN_REQUEST_REQUIRED")
    if type(request.run_id) is not str or not 1 <= len(request.run_id) <= 128:
        raise Rejected("EXACT_RUN_ID_REQUIRED")
    if type(request.stages) is not tuple or not request.stages:
        raise Rejected("NO_EXECUTED_DECISION_STAGE")
    if len(request.stages) > 2:
        raise Rejected("TOO_MANY_DECISION_STAGES")
    stages = [stage.stage for stage in request.stages]
    if len(stages) != len(set(stages)):
        raise Rejected("DUPLICATE_DECISION_STAGE")
    for stage in request.stages:
        _validate_stage(stage)


def composite_context(request: CompositeDecisionRunRequest) -> str:
    """Return the exact composite context hash for a validated request."""
    _validate_request(request)
    document = {
        "run_id": request.run_id,
        "coverage_revision_id": request.coverage_revision_id,
        "coverage_recording_fingerprint": request.coverage_recording_fingerprint,
        "stages": [
            {
                "stage": stage.stage,
                "decision_fingerprint": stage.decision_fingerprint,
                "inputs": stage.inputs,
                "outcome": stage.outcome,
                "evidence_refs": stage.evidence_refs,
            }
            for stage in request.stages
        ],
    }
    return _sha(_canonical(document))


def record_composite_audited_decision_run(
    target: Any,
    *,
    request: CompositeDecisionRunRequest,
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Record one or more immutable audited decision stages for one run."""
    _validate_request(request)
    if type(expected_context_sha256) is not str or len(expected_context_sha256) != 64:
        raise Rejected("EXACT_EXPECTED_CONTEXT_PIN_REQUIRED")
    if composite_context(request) != expected_context_sha256:
        raise Rejected("REVIEWED_COMPOSITE_DECISION_RUN_CONTEXT_CHANGED")

    recorded: list[dict[str, Any]] = []
    for stage in request.stages:
        stage_request = AuditedDecisionRunRequest(
            run_id=request.run_id,
            stage=stage.stage,
            decision_fingerprint=stage.decision_fingerprint,
            inputs=stage.inputs,
            outcome=stage.outcome,
            evidence_refs=stage.evidence_refs,
            coverage_revision_id=request.coverage_revision_id,
            coverage_recording_fingerprint=request.coverage_recording_fingerprint,
        )
        result = record_audited_decision_run(
            target,
            request=stage_request,
            expected_context_sha256=audited_decision_run_context(stage_request),
            actor_id=actor_id,
            code_revision=code_revision,
        )
        recorded.append(
            {
                "stage": stage.stage,
                "revision_id": result["revision_id"],
                "recording_fingerprint": result["recording_fingerprint"],
                "job_id": result["job_id"],
                "replayed": False,
                "decision_eligibility_asserted": False,
            }
        )

    return {
        "run_id": request.run_id,
        "stage_count": len(recorded),
        "stages": recorded,
        "decision_eligibility_asserted": False,
    }


def replay_composite_audited_decision_run(
    target: Any,
    *,
    run_id: str,
    stages: tuple[str, ...],
    expected_stage_revisions: dict[str, str],
    expected_stage_recording_fingerprints: dict[str, str],
) -> dict[str, Any]:
    """Exactly replay only requested stages that were previously recorded."""
    if type(run_id) is not str or not run_id:
        raise Rejected("EXACT_RUN_ID_REQUIRED")
    if type(stages) is not tuple or not stages:
        raise Rejected("NO_REQUESTED_DECISION_STAGE")
    if len(stages) != len(set(stages)):
        raise Rejected("DUPLICATE_REQUESTED_DECISION_STAGE")
    if type(expected_stage_revisions) is not dict or type(expected_stage_recording_fingerprints) is not dict:
        raise Rejected("EXACT_REPLAY_PINS_REQUIRED")

    results: list[dict[str, Any]] = []
    for stage in stages:
        if stage not in _SUPPORTED_STAGES:
            raise Rejected("UNSUPPORTED_STAGE")
        revision = expected_stage_revisions.get(stage)
        fingerprint = expected_stage_recording_fingerprints.get(stage)
        if revision is None or fingerprint is None:
            results.append(
                {
                    "stage": stage,
                    "replayed": False,
                    "reason": "STAGE_NOT_EXECUTED",
                    "decision_eligibility_asserted": False,
                }
            )
            continue
        replay = replay_audited_decision_run(
            target,
            run_id=run_id,
            stage=stage,
            expected_revision_id=revision,
            expected_recording_fingerprint=fingerprint,
        )
        results.append(
            {
                "stage": stage,
                "replayed": replay["replayed"],
                "reason": replay.get("reason"),
                "decision_fingerprint": replay.get("decision_fingerprint"),
                "evidence_refs": replay.get("evidence_refs"),
                "decision_eligibility_asserted": False,
            }
        )

    return {
        "run_id": run_id,
        "stages": results,
        "decision_eligibility_asserted": False,
    }
