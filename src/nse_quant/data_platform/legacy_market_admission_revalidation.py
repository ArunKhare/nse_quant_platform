"""Fresh publication policy and optional current-native checks of pinned captures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from nse_quant.data_platform import legacy_market_admission_capture as capture
from nse_quant.data_platform import legacy_market_publication as publication
from nse_quant.data_platform import legacy_market_publication_admission as policy
from nse_quant.data_platform.publication_admission import _request_from_json

VERSION = "legacy-research-captured-admission-revalidation@1"


@dataclass(frozen=True)
class LegacyAdmissionRevalidation:
    version: str
    capture_id: str
    status: str
    policy_status: str
    evidence_fingerprint: str
    archived_capture_verified: bool = True
    current_publication_checked: bool = True
    exact_receipt_reproduced: bool = True
    current_native_upstream_checked: bool = False
    research_analysis_authorized: bool = False
    decision_eligibility_asserted: bool = False
    replay_authenticity_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False


def revalidate_legacy_admission_capture(
    publications: Any,
    captures: Any,
    *,
    capture_id: str,
    expected_recording_fingerprint: str,
) -> LegacyAdmissionRevalidation:
    """Original capture bracketed around two actual fresh pinned publication assessments.

    Exact bytes must match, including a captured REJECTED point-in-time policy result.
    Changed/corrupt/operational sources raise, never downgrade to policy acceptance.
    """
    publication.foundation._separate(publications, captures)
    args = dict(
        capture_id=capture_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    before = capture.read_legacy_admission_capture(captures, **args)
    request = _request_from_json(json.loads(before.request_json))
    fresh = capture._observe(publications, before.pins, request)
    repeated = capture._observe(publications, before.pins, request)
    after = capture.read_legacy_admission_capture(captures, **args)
    if before != after:
        raise ValueError("LEGACY_CAPTURE_CHANGED_DURING_REVALIDATION")
    if fresh != repeated or fresh != before.receipt_bytes:
        raise ValueError("LEGACY_CAPTURE_CURRENT_PUBLICATION_ASSESSMENT_DRIFT")
    receipt = policy.replay_legacy_admission(fresh, expected_receipt_id=before.receipt_id)
    fingerprint = publication._hash(
        [
            VERSION,
            before.recording_fingerprint,
            after.recording_fingerprint,
            publication.bundle.gold.sha(fresh),
            publication.bundle.gold.sha(repeated),
            "CURRENT_PUBLICATION_NOT_CURRENT_NATIVE_UPSTREAM",
        ]
    )
    return LegacyAdmissionRevalidation(
        VERSION,
        capture_id,
        "matched_rejected_input" if receipt.status == "REJECTED" else "matched_research_input",
        receipt.status,
        fingerprint,
    )


def revalidate_legacy_admission_upstream(
    bronze: Any,
    silver: Any,
    gold: Any,
    publications: Any,
    captures: Any,
    *,
    capture_id: str,
    expected_recording_fingerprint: str,
) -> LegacyAdmissionRevalidation:
    """Adds actual current native publication revalidation, NEVER current legacy SQL."""
    for source in (bronze, silver, gold, publications):
        publication.foundation._separate(source, captures)
    args = dict(
        capture_id=capture_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    archived = capture.read_legacy_admission_capture(captures, **args)
    first = revalidate_legacy_admission_capture(publications, captures, **args)
    one = publication.revalidate_legacy_research_publication(
        bronze, silver, gold, publications, **archived.pins.arguments()
    )
    two = publication.revalidate_legacy_research_publication(
        bronze, silver, gold, publications, **archived.pins.arguments()
    )
    second = revalidate_legacy_admission_capture(publications, captures, **args)
    final = capture.read_legacy_admission_capture(captures, **args)
    if one != two or first != second or final != archived:
        raise ValueError("LEGACY_CAPTURE_CURRENT_NATIVE_UPSTREAM_DRIFT")
    fingerprint = publication._hash(
        [
            VERSION,
            first.evidence_fingerprint,
            second.evidence_fingerprint,
            one.recording_fingerprint,
            two.recording_fingerprint,
            "CURRENT_NATIVE_UPSTREAM_CHECKED",
        ]
    )
    return LegacyAdmissionRevalidation(
        VERSION,
        capture_id,
        first.status,
        first.policy_status,
        fingerprint,
        current_native_upstream_checked=True,
    )
