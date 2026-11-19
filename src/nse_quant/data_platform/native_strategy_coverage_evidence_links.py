"""Validate coverage evidence links for native strategy requirements.

Validates that every covered native requirement has a well-formed Silver
evidence link with exact revision and recording-fingerprint pins. This is
observational validation only: no eligibility, live trading, healing, backfill,
adoption, or execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-strategy-coverage-evidence-links@1"
COMMAND = "validate.native_strategy_coverage_evidence_links@1"


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _validate_evidence_ref(requirement: str, evidence_ref: object) -> None:
    if type(evidence_ref) is not str or not evidence_ref:
        raise Rejected("COVERAGE_EVIDENCE_REF_REQUIRED")
    if not evidence_ref.startswith("silver://"):
        raise Rejected("COVERAGE_EVIDENCE_REF_SCHEME_INVALID")
    if not evidence_ref.startswith(f"silver://{requirement}?"):
        raise Rejected("COVERAGE_EVIDENCE_REF_REQUIREMENT_MISMATCH")
    query = evidence_ref.split("?", 1)[1]
    parameters = dict(item.split("=", 1) for item in query.split("&") if "=" in item)
    if not _pin(parameters.get("revision_id")):
        raise Rejected("COVERAGE_EVIDENCE_REVISION_INVALID")
    if not _pin(parameters.get("recording_fingerprint")):
        raise Rejected("COVERAGE_EVIDENCE_FINGERPRINT_INVALID")
    if not parameters.get("row_count", "").isdigit():
        raise Rejected("COVERAGE_EVIDENCE_ROW_COUNT_INVALID")


def validate_coverage_evidence_links(
    coverage_report: dict[str, Any],
) -> dict[str, Any]:
    """Validate evidence links for every covered native requirement."""
    if type(coverage_report) is not dict:
        raise Rejected("COVERAGE_REPORT_REQUIRED")
    if coverage_report.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if coverage_report.get("decision_eligibility_asserted") is not False:
        raise Rejected("COVERAGE_ELIGIBILITY_FORBIDDEN")
    covered = coverage_report.get("covered")
    if type(covered) is not list:
        raise Rejected("COVERAGE_COVERED_REQUIRED")
    evidence_refs = coverage_report.get("evidence_refs")
    if type(evidence_refs) is not dict:
        raise Rejected("COVERAGE_EVIDENCE_REFS_REQUIRED")
    for requirement in covered:
        if type(requirement) is not str or not requirement:
            raise Rejected("COVERAGE_REQUIREMENT_INVALID")
        if requirement not in evidence_refs:
            raise Rejected("COVERAGE_EVIDENCE_REF_MISSING")
        _validate_evidence_ref(requirement, evidence_refs[requirement])
    return {
        "valid": True,
        "version": VERSION,
        "covered_count": len(covered),
        "decision_eligibility_asserted": False,
    }


def coverage_evidence_links_context(coverage_report: dict[str, Any]) -> str:
    """Return the exact context hash for validated evidence links."""
    import hashlib

    validate_coverage_evidence_links(coverage_report)
    canonical = json.dumps(
        coverage_report,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
