"""Audited native decision-run coverage reconciliation; observational only.

Links a recorded and replayed composite audited decision run to the current
Silver-backed native strategy input coverage report. Never grants eligibility,
heals a gap, backfills evidence, or authorizes execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import (
    DEFINITION_SHA256,
    REQUIREMENTS,
    STAGES,
    STRATEGY,
    VERSION,
)

_SUPPORTED_STAGES = frozenset({"strategy", "portfolio_risk"})
_NEVER_AUTO_COVERABLE = frozenset({"authoritative_identity_and_time"})


@dataclass(frozen=True)
class DecisionRunReconciliationRequest:
    run_id: str
    coverage_revision_id: str
    coverage_recording_fingerprint: str
    stages: tuple[str, ...]
    stage_revisions: dict[str, str]
    stage_recording_fingerprints: dict[str, str]


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _validate_coverage(coverage_report: dict[str, Any]) -> None:
    if type(coverage_report) is not dict:
        raise Rejected("COVERAGE_REPORT_REQUIRED")
    if coverage_report.get("version") != VERSION:
        raise Rejected("COVERAGE_VERSION_MISMATCH")
    if coverage_report.get("strategy") != STRATEGY:
        raise Rejected("COVERAGE_STRATEGY_MISMATCH")
    if coverage_report.get("definition_sha256") != DEFINITION_SHA256:
        raise Rejected("COVERAGE_DEFINITION_MISMATCH")
    if coverage_report.get("stages") != STAGES:
        raise Rejected("COVERAGE_STAGE_MISMATCH")

    covered = coverage_report.get("covered", [])
    unlinked = coverage_report.get("unlinked", [])
    missing = coverage_report.get("missing", [])
    evidence_refs = coverage_report.get("evidence_refs", {})
    if type(covered) not in (list, tuple, set, frozenset):
        raise Rejected("COVERAGE_COVERED_COLLECTION_REQUIRED")
    if type(unlinked) not in (list, tuple, set, frozenset):
        raise Rejected("COVERAGE_UNLINKED_COLLECTION_REQUIRED")
    if type(missing) not in (list, tuple, set, frozenset):
        raise Rejected("COVERAGE_MISSING_COLLECTION_REQUIRED")
    if type(evidence_refs) is not dict:
        raise Rejected("COVERAGE_EVIDENCE_REFS_REQUIRED")

    known = {requirement_id for requirement_id, _source, _need in REQUIREMENTS}
    for collection, label in (
        (covered, "COVERED"),
        (unlinked, "UNLINKED"),
        (missing, "MISSING"),
    ):
        unknown = sorted(set(collection) - known)
        if unknown:
            raise Rejected(f"UNKNOWN_{label}_REQUIREMENT_ID")
    for key, value in evidence_refs.items():
        if type(key) is not str or key not in known or type(value) is not str or not value:
            raise Rejected("EXACT_COVERAGE_EVIDENCE_REF_REQUIRED")
    if "authoritative_identity_and_time" in covered:
        raise Rejected("AUTHORITATIVE_IDENTITY_NOT_AUTO_COVERABLE")


def _validate_request(request: DecisionRunReconciliationRequest) -> None:
    if type(request) is not DecisionRunReconciliationRequest:
        raise Rejected("TYPED_RECONCILIATION_REQUEST_REQUIRED")
    if type(request.run_id) is not str or not 1 <= len(request.run_id) <= 128:
        raise Rejected("EXACT_RUN_ID_REQUIRED")
    if not _pin(request.coverage_revision_id):
        raise Rejected("EXACT_COVERAGE_REVISION_PIN_REQUIRED")
    if not _pin(request.coverage_recording_fingerprint):
        raise Rejected("EXACT_COVERAGE_RECORDING_FINGERPRINT_REQUIRED")
    if type(request.stages) is not tuple or not request.stages:
        raise Rejected("NO_REQUESTED_DECISION_STAGE")
    if len(request.stages) != len(set(request.stages)):
        raise Rejected("DUPLICATE_REQUESTED_DECISION_STAGE")
    if any(stage not in _SUPPORTED_STAGES for stage in request.stages):
        raise Rejected("UNSUPPORTED_STAGE")
    if type(request.stage_revisions) is not dict or type(request.stage_recording_fingerprints) is not dict:
        raise Rejected("EXACT_REPLAY_PINS_REQUIRED")
    for stage in request.stages:
        revision = request.stage_revisions.get(stage)
        fingerprint = request.stage_recording_fingerprints.get(stage)
        if revision is not None and not _pin(revision):
            raise Rejected("EXACT_STAGE_REVISION_PIN_REQUIRED")
        if fingerprint is not None and not _pin(fingerprint):
            raise Rejected("EXACT_STAGE_RECORDING_FINGERPRINT_REQUIRED")


def reconcile_audited_decision_run(
    *,
    coverage_report: dict[str, Any],
    run_id: str,
    stages: tuple[str, ...],
    stage_revisions: dict[str, str],
    stage_recording_fingerprints: dict[str, str],
) -> dict[str, Any]:
    """Reconcile a decision run with exact Silver-backed coverage evidence."""
    request = DecisionRunReconciliationRequest(
        run_id=run_id,
        coverage_revision_id=coverage_report.get("revision_id", ""),
        coverage_recording_fingerprint=coverage_report.get("recording_fingerprint", ""),
        stages=stages,
        stage_revisions=stage_revisions,
        stage_recording_fingerprints=stage_recording_fingerprints,
    )
    _validate_coverage(coverage_report)
    _validate_request(request)

    covered = list(coverage_report["covered"])
    unlinked = list(coverage_report["unlinked"])
    missing = list(coverage_report["missing"])
    evidence_refs = dict(coverage_report["evidence_refs"])

    stage_results: list[dict[str, Any]] = []
    for stage in stages:
        revision = stage_revisions.get(stage)
        fingerprint = stage_recording_fingerprints.get(stage)
        if revision is None or fingerprint is None:
            stage_results.append(
                {
                    "stage": stage,
                    "replayed": False,
                    "reason": "STAGE_NOT_EXECUTED",
                    "decision_eligibility_asserted": False,
                }
            )
            continue
        stage_results.append(
            {
                "stage": stage,
                "replayed": True,
                "revision_id": revision,
                "recording_fingerprint": fingerprint,
                "decision_eligibility_asserted": False,
            }
        )

    complete = coverage_report.get("complete") is True and all(item["replayed"] for item in stage_results)

    return {
        "version": VERSION,
        "strategy": STRATEGY,
        "run_id": run_id,
        "coverage": {
            "revision_id": request.coverage_revision_id,
            "recording_fingerprint": request.coverage_recording_fingerprint,
            "covered": covered,
            "unlinked": unlinked,
            "missing": missing,
            "evidence_refs": evidence_refs,
            "complete": coverage_report.get("complete") is True,
        },
        "stages": stage_results,
        "complete": complete,
        "decision_eligibility_asserted": False,
    }
