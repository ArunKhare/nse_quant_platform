"""All-or-nothing, two-pass current Gold snapshot assembly. No persistence."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from nse_quant.data_platform.feature_bundle import (
    GOLD_READER_VERSION,
    MAX_MEMBERS,
    QuoteBundleMember,
    QuoteFeatureBundle,
    canonical,
    digest,
    make_quote_bundle,
    valid_pin,
)
from nse_quant.data_platform.gold_quote_reader import GoldQuoteEvidence, read_quote_price_build


class BundleAssemblyRejected(ValueError):
    def __init__(self, reason_code: str, build_id: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.build_id = build_id


def _snapshot(evidence: GoldQuoteEvidence, build_id: str) -> QuoteBundleMember:
    if (
        evidence.reader_version != GOLD_READER_VERSION
        or evidence.build_id != build_id
        or evidence.status != "verified_current"
        or evidence.reason_code != "SOURCE_RECOMPUTED"
        or evidence.active_build_ids != (build_id,)
        or evidence.evidence_fingerprint is None
        or not valid_pin(evidence.evidence_fingerprint)
        or evidence.publication_asserted is not False
        or evidence.historical_validity_asserted is not False
        or evidence.decision_eligibility_asserted is not False
        or evidence.candidate is None
        or evidence.candidate.status != "candidate"
        or evidence.candidate.build_id != build_id
    ):
        raise BundleAssemblyRejected("BUNDLE_MEMBER_NOT_CURRENT_CANDIDATE", build_id)
    candidate_json = canonical(asdict(evidence.candidate))
    return QuoteBundleMember(
        build_id,
        evidence.reader_version,
        evidence.evidence_fingerprint,
        evidence.successful_attempt_job_ids,
        digest(candidate_json.encode()),
        candidate_json,
    )


def assemble_quote_bundle(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    gold: Any,
    *,
    build_ids: tuple[str, ...],
) -> QuoteFeatureBundle:
    """Read-only sequential revalidation; no source calls on invalid arguments.

    Two passes detect observed drift; they are NOT an atomic cross-database
    snapshot, simultaneous market observation, publication or replay barrier.
    Reader errors propagate. No automatic retry, partial membership or fallback.
    """
    if (
        not isinstance(build_ids, tuple)
        or not 1 <= len(build_ids) <= MAX_MEMBERS
        or any(not valid_pin(pin) for pin in build_ids)
        or len(set(build_ids)) != len(build_ids)
    ):
        raise ValueError("EXPLICIT_UNIQUE_BOUNDED_BUILD_PINS_REQUIRED")
    members = []
    for pin in sorted(build_ids):
        evidence = read_quote_price_build(
            bronze,
            frame_silver,
            reference_silver,
            assessments,
            gold,
            build_id=pin,
        )
        members.append(_snapshot(evidence, pin))
    # Validate full content/membership before a potentially expensive second pass.
    bundle = make_quote_bundle(tuple(members))
    for member in bundle.members:
        evidence = read_quote_price_build(
            bronze,
            frame_silver,
            reference_silver,
            assessments,
            gold,
            build_id=member.build_id,
        )
        if _snapshot(evidence, member.build_id) != member:
            raise BundleAssemblyRejected("BUNDLE_MEMBER_CHANGED_DURING_ASSEMBLY", member.build_id)
    return bundle
