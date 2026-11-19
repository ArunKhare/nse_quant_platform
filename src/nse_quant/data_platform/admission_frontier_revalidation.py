"""Strict observed capture-frontier guard around committed native revalidation @1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nse_quant.data_platform import admission_revalidation as native
from nse_quant.data_platform.admission_frontier import (
    AdmissionFrontier,
    FrontierReviewRequired,
    observe_admission_frontier,
)
from nse_quant.data_platform.feature_bundle import valid_pin
from nse_quant.data_platform.publication_admission import AdmissionRequest

VERSION = "frontier-guarded-admission-revalidation@1"


@dataclass(frozen=True)
class FrontierRevalidation:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    before: AdmissionFrontier | None = None
    after: AdmissionFrontier | None = None
    native_result: native.AdmissionRevalidation | None = None
    capture_frontier_unchanged_observed: bool = False
    research_policy_satisfied: bool = False
    research_analysis_authorized: bool = False
    decision_eligibility_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False
    authenticity_asserted: bool = False


def revalidate_with_capture_frontier(
    publications: Any,
    captures: Any,
    *,
    receipt_id: str,
    publication_id: str,
    request: AdmissionRequest,
) -> FrontierRevalidation:
    """Three independent calls, not an atomic cross-resource snapshot or permit.

    Whole dedicated capture DB changes conservatively block even for unrelated
    requests or successful exact retries. Original native result remains evidence,
    but top-level status/flags govern this stricter observational result.
    """
    if native.VERSION != "captured-publication-request-revalidation@1":
        raise ValueError("UNSUPPORTED_FRONTIER_REVALIDATION_DEPENDENCY")
    if not valid_pin(receipt_id) or not valid_pin(publication_id):
        raise ValueError("EXACT_FRONTIER_REVALIDATION_PINS_REQUIRED")
    if not isinstance(request, AdmissionRequest):
        raise TypeError("TYPED_FRONTIER_REVALIDATION_REQUEST_REQUIRED")
    AdmissionRequest(request.use_case, request.knowledge_cutoff, request.economic_at)
    before = after = None
    result = None
    try:
        before = observe_admission_frontier(captures)
        result = native.revalidate_captured_publication_use(
            publications,
            captures,
            receipt_id=receipt_id,
            publication_id=publication_id,
            request=request,
        )
        after = observe_admission_frontier(captures)
    except FrontierReviewRequired as error:
        return FrontierRevalidation(
            VERSION,
            "review_required",
            (str(error),),
            before,
            after,
            result,
        )
    if before.fingerprint != after.fingerprint:
        return FrontierRevalidation(
            VERSION,
            "review_required",
            ("CAPTURE_DATABASE_FRONTIER_CHANGED",),
            before,
            after,
            result,
        )
    return FrontierRevalidation(
        VERSION,
        result.status,
        result.reason_codes,
        before,
        after,
        result,
        True,
        result.status == "matched_research_input" and result.research_policy_satisfied is True,
    )
