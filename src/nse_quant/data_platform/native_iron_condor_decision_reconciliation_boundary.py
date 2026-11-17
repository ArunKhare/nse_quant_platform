"""Integrate the authoritative identity/time boundary into reconciliation.

Builds an extended reconciliation document that carries independently evidenced
authoritative identity, derivative binding, and authorized revocation, then
persists and replays it through the existing reconciliation Silver recorder.
No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    VERSION as BASE_RECONCILIATION_VERSION,
)
from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    reconciliation_context,
    record_audited_decision_reconciliation,
    replay_audited_decision_reconciliation,
)
from nse_quant.data_platform.native_authoritative_identity_time_boundary import (
    authoritative_boundary_context,
    validate_authoritative_identity_time_boundary,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-iron-condor-decision-reconciliation-boundary@1"
COMMAND = "record.native_iron_condor_decision_reconciliation_boundary@1"


def build_reconciliation_with_authoritative_boundary(
    reconciliation: dict[str, Any],
    boundary: dict[str, Any],
) -> dict[str, Any]:
    """Return an extended reconciliation document with boundary evidence."""
    if type(reconciliation) is not dict:
        raise Rejected("RECONCILIATION_DOCUMENT_REQUIRED")
    if type(boundary) is not dict:
        raise Rejected("AUTHORITATIVE_BOUNDARY_DOCUMENT_REQUIRED")
    if reconciliation.get("version") != BASE_RECONCILIATION_VERSION:
        raise Rejected("RECONCILIATION_BOUNDARY_VERSION_MISMATCH")
    if reconciliation.get("strategy") != boundary.get("strategy"):
        raise Rejected("RECONCILIATION_BOUNDARY_STRATEGY_MISMATCH")
    if reconciliation.get("run_id") != boundary.get("run_id"):
        raise Rejected("RECONCILIATION_BOUNDARY_RUN_MISMATCH")
    if reconciliation.get("complete") is True:
        raise Rejected("RECONCILIATION_COMPLETION_NOT_ASSERTABLE")
    if reconciliation.get("decision_eligibility_asserted") is not False:
        raise Rejected("RECONCILIATION_ELIGIBILITY_FORBIDDEN")

    validate_authoritative_identity_time_boundary(boundary)
    extended = dict(reconciliation)
    extended["version"] = BASE_RECONCILIATION_VERSION
    extended["authoritative_boundary"] = dict(boundary)
    extended["authoritative_boundary_context"] = authoritative_boundary_context(boundary)
    return extended


def record_reconciliation_with_authoritative_boundary(
    target: Any,
    *,
    reconciliation: dict[str, Any],
    boundary: dict[str, Any],
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Persist an extended reconciliation with authoritative boundary evidence."""
    extended = build_reconciliation_with_authoritative_boundary(
        reconciliation,
        boundary,
    )
    if reconciliation_context(extended) != expected_context_sha256:
        raise Rejected("REVIEWED_RECONCILIATION_CONTEXT_CHANGED")
    return record_audited_decision_reconciliation(
        target,
        reconciliation=extended,
        expected_context_sha256=expected_context_sha256,
        actor_id=actor_id,
        code_revision=code_revision,
    )


def replay_reconciliation_with_authoritative_boundary(
    target: Any,
    *,
    run_id: str,
    expected_revision_id: str,
    expected_recording_fingerprint: str,
) -> dict[str, Any]:
    """Exactly replay an extended reconciliation with boundary evidence."""
    result = replay_audited_decision_reconciliation(
        target,
        run_id=run_id,
        expected_revision_id=expected_revision_id,
        expected_recording_fingerprint=expected_recording_fingerprint,
    )
    document = result["reconciliation"]
    boundary = document.get("authoritative_boundary")
    if type(boundary) is not dict:
        raise Rejected("AUTHORITATIVE_BOUNDARY_DOCUMENT_REQUIRED")
    if document.get("authoritative_boundary_context") != authoritative_boundary_context(boundary):
        raise Rejected("AUTHORITATIVE_BOUNDARY_CONTEXT_CHANGED")
    validate_authoritative_identity_time_boundary(boundary)
    return {
        "run_id": run_id,
        "replayed": True,
        "reconciliation": document,
        "authoritative_boundary": boundary,
        "decision_eligibility_asserted": False,
    }
