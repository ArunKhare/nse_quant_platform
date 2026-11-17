"""Persisted, evidence-linked audited native decision runs; observational only.

This module records and exactly replays only strategy or portfolio-risk stages
that actually ran. It never grants eligibility, enables live trading, heals a
failed/incomplete/unlinked/orphan obligation, or authorizes execution.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import (
    DEFINITION_SHA256,
    STAGES,
    STRATEGY,
    VERSION,
)

_SUPPORTED_STAGES = frozenset({"strategy", "portfolio_risk"})
_NEVER_AUTO_COVERABLE = frozenset({"authoritative_identity_and_time"})


class DecisionStageRun(BaseModel):
    stage: str
    decision_fingerprint: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    outcome: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: dict[str, str] = Field(default_factory=dict)
    executed: bool


class AuditedDecisionRun(BaseModel):
    run_id: str
    strategy: str
    coverage_revision_id: str
    coverage_recording_fingerprint: str
    stages: list[DecisionStageRun] = Field(default_factory=list)
    decision_eligibility_asserted: bool = False


def ensure_no_point_in_time_decision(outcome: dict[str, Any]) -> None:
    """Reject the forbidden POINT_IN_TIME_DECISION outcome type."""
    if outcome.get("decision_type") == "POINT_IN_TIME_DECISION":
        raise Rejected("POINT_IN_TIME_DECISION_REJECTED")


def _validate_coverage_identity(coverage_report: dict[str, Any]) -> None:
    if coverage_report.get("version") != VERSION:
        raise Rejected("COVERAGE_VERSION_MISMATCH")
    if coverage_report.get("strategy") != STRATEGY:
        raise Rejected("COVERAGE_STRATEGY_MISMATCH")
    if coverage_report.get("definition_sha256") != DEFINITION_SHA256:
        raise Rejected("COVERAGE_DEFINITION_MISMATCH")
    if coverage_report.get("stages") != STAGES:
        raise Rejected("COVERAGE_STAGE_MISMATCH")

    revision_id = coverage_report.get("revision_id")
    recording_fingerprint = coverage_report.get("recording_fingerprint")
    if type(revision_id) is not str or len(revision_id) != 64:
        raise Rejected("COVERAGE_REVISION_PIN_REQUIRED")
    if type(recording_fingerprint) is not str or len(recording_fingerprint) != 64:
        raise Rejected("COVERAGE_RECORDING_FINGERPRINT_REQUIRED")


def bind_decision_run_to_coverage(
    *,
    coverage_report: dict[str, Any],
    stage: str,
    required_requirement_ids: frozenset[str],
) -> dict[str, str]:
    """Bind a decision stage to exact Silver-backed coverage evidence.

    This is observational only. It never grants eligibility, heals a gap,
    backfills evidence, or authorizes execution.
    """
    if stage not in _SUPPORTED_STAGES:
        raise Rejected("UNSUPPORTED_STAGE")
    if type(coverage_report) is not dict:
        raise Rejected("COVERAGE_REPORT_REQUIRED")
    if type(required_requirement_ids) is not frozenset:
        raise Rejected("EXACT_REQUIREMENT_IDS_REQUIRED")

    _validate_coverage_identity(coverage_report)

    covered = coverage_report.get("covered", [])
    evidence_refs = coverage_report.get("evidence_refs", {})
    if type(covered) not in (list, tuple, set, frozenset):
        raise Rejected("COVERAGE_COVERED_COLLECTION_REQUIRED")
    if type(evidence_refs) is not dict:
        raise Rejected("COVERAGE_EVIDENCE_REFS_REQUIRED")

    bound: dict[str, str] = {}
    for requirement_id in sorted(required_requirement_ids):
        if requirement_id in _NEVER_AUTO_COVERABLE:
            raise Rejected("AUTHORITATIVE_IDENTITY_NOT_AUTO_COVERABLE")
        if requirement_id not in covered:
            raise Rejected("REQUIRED_COVERAGE_MISSING")
        evidence_ref = evidence_refs.get(requirement_id)
        if type(evidence_ref) is not str or not evidence_ref:
            raise Rejected("REQUIRED_COVERAGE_EVIDENCE_MISSING")
        bound[requirement_id] = evidence_ref

    return bound
