"""Actual lifecycle/publication binding of supplied time claims; research refusal preserved."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform import observed_key_lifecycle as lifecycle
from nse_quant.data_platform import publication_admission as admission
from nse_quant.data_platform import quote_publication_reader as publications
from nse_quant.data_platform import signed_temporal_evidence as temporal

if TYPE_CHECKING:
    from nse_quant.data_platform.observed_key_lifecycle import LifecycleScope, ObservedKeyLifecycle
    from nse_quant.data_platform.publication_admission import AdmissionReceipt
    from nse_quant.data_platform.quote_publication_reader import ResearchPublicationEvidence
    from nse_quant.data_platform.signed_temporal_evidence import TemporalEvaluation, TemporalRequest

VERSION = "native-publication-temporal-declarations@1"
MAX_PUBLICATION_CONTEXT_BYTES = 16777216


@dataclass(frozen=True)
class NativePublicationTemporal:
    version: str
    publication_id: str
    expected_publication_evidence_fingerprint: str
    status: str
    reason_codes: tuple[str, ...]
    before: ResearchPublicationEvidence | None = None
    after: ResearchPublicationEvidence | None = None
    lifecycle_observations: tuple[ObservedKeyLifecycle, ...] = ()
    temporal_evaluation: TemporalEvaluation | None = None
    temporal_receipt: bytes | None = None
    admission_receipt: AdmissionReceipt | None = None
    evidence_fingerprint: str | None = None
    publication_snapshot_rechecked: bool = False
    decision_refusal_reproduced: bool = False
    independent_time_evidence_verified: bool = False
    availability_evidence_verified: bool = False
    economic_validity_verified: bool = False
    root_authority_authenticated: bool = False
    issuer_authenticated: bool = False
    namespace_authority_verified: bool = False
    identity_verified: bool = False
    historical_validity_asserted: bool = False
    authorized_revocation_asserted: bool = False
    source_current_checked: bool = False
    decision_eligibility_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False
    canonical_contract_id: None = None


def assess_native_publication_temporal(
    publication_source: Any,
    *,
    publication_id: str,
    expected_publication_evidence_fingerprint: str,
    lifecycle_records: tuple[bytes, ...],
    expected_lifecycle_record_sha256s: tuple[str, ...],
    root_public_key: bytes,
    expected_root_key_sha256: str,
    scope: LifecycleScope,
    declarations: tuple[bytes, ...],
    expected_declaration_sha256s: tuple[str, ...],
    expected_declaration_tip_sha256: str,
    support_blobs: tuple[bytes, ...],
    request: TemporalRequest,
) -> NativePublicationTemporal:
    """No caller source/lifecycle DTOs, signer override, writes or admission override.

    Verify full actual key chain; derive each declaration key from its exact chain prefix.
    Final declaration signer must still be active in the complete supplied chain.
    Bracket claims with actual native publication reads; compare the actual admission
    assessment's complete frozen source too. Agreement is not cross-resource atomicity.
    Lifecycle/temporal histories are only supplied sets, never globally latest/complete.
    """
    if (
        lifecycle.VERSION != "observed-governance-key-lifecycle@1"
        or lifecycle.MAX_EVENTS != 64
        or admission.POLICY_VERSION != "research-publication-admission@1"
        or publications.READER_VERSION != "research-quote-publication-consumer@1"
        or temporal.VERSION != "signed-publication-temporal-evidence@1"
    ):
        raise temporal.TemporalEvidenceRejected("UNSUPPORTED_NATIVE_TEMPORAL_DEPENDENCY")
    if (
        not temporal.pin(publication_id)
        or not temporal.pin(expected_publication_evidence_fingerprint)
        or type(request) is not temporal.TemporalRequest
    ):
        raise temporal.TemporalEvidenceRejected("NATIVE_TEMPORAL_EXACT_PINS_AND_REQUEST")
    if (
        type(declarations) is not tuple
        or not 1 <= len(declarations) <= temporal.MAX_RECORDS
        or type(expected_declaration_sha256s) is not tuple
        or len(expected_declaration_sha256s) != len(declarations)
        or any(not temporal.pin(x) for x in expected_declaration_sha256s)
        or not temporal.pin(expected_declaration_tip_sha256)
    ):
        raise temporal.TemporalEvidenceRejected("NATIVE_TEMPORAL_DECLARATION_BOUND")
    if any(
        type(x) is not bytes or not 0 < len(x) <= temporal.MAX_RECORD_BYTES for x in declarations
    ):
        raise temporal.TemporalEvidenceRejected("NATIVE_TEMPORAL_DECLARATION_BOUND")
    if sum(len(x) for x in declarations) > temporal.MAX_RECORD_TOTAL:
        raise temporal.TemporalEvidenceRejected("NATIVE_TEMPORAL_DECLARATION_AGGREGATE")
    full = lifecycle.inspect_key_lifecycle(
        lifecycle_records,
        expected_record_sha256s=expected_lifecycle_record_sha256s,
        root_public_key=root_public_key,
        expected_root_key_sha256=expected_root_key_sha256,
        scope=scope,
    )
    facts: dict[str, Any] = dict(lifecycle_observations=(full,))

    def report(reasons: tuple[str, ...], **extra: Any) -> NativePublicationTemporal:
        return NativePublicationTemporal(
            VERSION,
            publication_id,
            expected_publication_evidence_fingerprint,
            "review_required",
            reasons,
            **(facts | extra),
        )

    if full.active_public_key_hex is None:
        return report(("SUPPLIED_LIFECYCLE_TIP_REVOKED",))
    first = publications.read_research_publication(
        publication_source,
        publication_id=publication_id,
    )
    first_raw = temporal.canonical(asdict(first))
    if not 0 < len(first_raw) <= MAX_PUBLICATION_CONTEXT_BYTES:
        raise temporal.TemporalEvidenceRejected("NATIVE_TEMPORAL_PUBLICATION_CONTEXT_BOUND")
    facts["before"] = first
    if (
        first.status != "verified_research_snapshot"
        or first.research_publication_verified is not True
        or first.evidence_fingerprint != expected_publication_evidence_fingerprint
        or first.bundle_id is None
    ):
        return report(("EXACT_REVIEWED_PUBLICATION_NOT_VERIFIED",))
    subject = temporal.TemporalSubject(
        scope.namespace,
        scope.asset_kind,
        publication_id,
        first.bundle_id,
        expected_publication_evidence_fingerprint,
    )
    observations: list[lifecycle.ObservedKeyLifecycle] = [full]
    keys: list[bytes] = []
    for record, pin in zip(declarations, expected_declaration_sha256s, strict=True):
        if temporal.sha(record) != pin:
            raise temporal.TemporalEvidenceRejected("TEMPORAL_RECORD_PIN_MISMATCH")
        _raw, body, _signature = temporal.declaration_document(record)
        position = body.get("lifecycle_tip_sha256")
        if position not in expected_lifecycle_record_sha256s:
            return report(("DECLARATION_LIFECYCLE_PIN_NOT_IN_SUPPLIED_CHAIN",))
        index = expected_lifecycle_record_sha256s.index(position) + 1
        observed = lifecycle.inspect_key_lifecycle(
            lifecycle_records[:index],
            expected_record_sha256s=expected_lifecycle_record_sha256s[:index],
            root_public_key=root_public_key,
            expected_root_key_sha256=expected_root_key_sha256,
            scope=scope,
        )
        observations.append(observed)
        if observed.active_public_key_hex is None:
            return report(("DECLARATION_SIGNING_PREFIX_REVOKED",))
        keys.append(bytes.fromhex(observed.active_public_key_hex))
    facts["lifecycle_observations"] = tuple(observations)
    if keys[-1].hex() != full.active_public_key_hex:
        return report(("FINAL_DECLARATION_SIGNER_RETIRED_IN_SUPPLIED_CHAIN",))
    raw_receipt = temporal.encode_temporal_receipt(
        declarations,
        expected_record_sha256s=expected_declaration_sha256s,
        expected_tip_sha256=expected_declaration_tip_sha256,
        verification_keys=tuple(keys),
        support_blobs=support_blobs,
        subject=subject,
        request=request,
    )
    evaluated = temporal.replay_temporal_receipt(
        raw_receipt,
        expected_receipt_sha256=temporal.sha(raw_receipt),
    )
    facts.update(temporal_evaluation=evaluated, temporal_receipt=raw_receipt)
    second = publications.read_research_publication(
        publication_source,
        publication_id=publication_id,
    )
    second_raw = temporal.canonical(asdict(second))
    if not 0 < len(second_raw) <= MAX_PUBLICATION_CONTEXT_BYTES:
        raise temporal.TemporalEvidenceRejected("NATIVE_TEMPORAL_PUBLICATION_CONTEXT_BOUND")
    facts["after"] = second
    if second_raw != first_raw:
        return report(("PUBLICATION_CONTEXT_CHANGED_DURING_TEMPORAL_CHECK",))
    facts["publication_snapshot_rechecked"] = True
    decision = admission.assess_publication_use(
        publication_source,
        publication_id=publication_id,
        request=admission.AdmissionRequest(
            admission.POINT_IN_TIME,
            request.knowledge_cutoff,
            request.economic_at,
        ),
    )
    encoded = admission.encode_admission_receipt(decision)
    replayed = admission.replay_admission_receipt(
        encoded,
        expected_receipt_id=decision.receipt_id,
    )
    if replayed != decision:
        raise temporal.TemporalEvidenceRejected("NATIVE_TEMPORAL_ADMISSION_REPLAY_MISMATCH")
    frozen = json_source(decision.frozen_input_json)
    facts["admission_receipt"] = decision
    if temporal.canonical(frozen) != second_raw:
        return report(("ADMISSION_SOURCE_CHANGED_AFTER_TEMPORAL_CHECK",))
    if (
        decision.status != "REJECTED"
        or decision.decision_eligibility_asserted is not False
        or decision.availability_evidence_verified is not False
        or decision.economic_validity_verified is not False
    ):
        raise temporal.TemporalEvidenceRejected("UNSUPPORTED_TEMPORAL_RESEARCH_ADMISSION_RESULT")
    reasons = () if evaluated.declared_time_constraints_satisfied else evaluated.reason_codes
    reasons += decision.reason_codes
    fingerprint = temporal.sha(
        temporal.canonical(
            [
                VERSION,
                publication_id,
                expected_publication_evidence_fingerprint,
                [asdict(x) for x in observations],
                temporal.sha(raw_receipt),
                asdict(first),
                asdict(second),
                asdict(decision),
                reasons,
            ]
        )
    )
    return NativePublicationTemporal(
        VERSION,
        publication_id,
        expected_publication_evidence_fingerprint,
        "refused_existing_research_contract",
        reasons,
        evidence_fingerprint=fingerprint,
        decision_refusal_reproduced=True,
        **facts,
    )


def json_source(frozen: str) -> object:
    import json

    return json.loads(frozen)["source"]
