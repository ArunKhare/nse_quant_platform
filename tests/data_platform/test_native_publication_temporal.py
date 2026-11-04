"""Actual native producer/publication/lifecycle/admission integration; no source substitutes."""

from datetime import timedelta

import duckdb
import pytest
from native_failure_acceptance_lab import NativeFailureLab, table
from temporal_evidence_fixture import (
    SUPPORT,
    T,
    declaration,
    key,
    lifecycle_event,
    public,
)

from nse_quant.data_platform import signed_temporal_evidence as temporal
from nse_quant.data_platform.native_publication_temporal import assess_native_publication_temporal
from nse_quant.data_platform.publication_admission import (
    encode_admission_receipt,
    replay_admission_receipt,
)


@pytest.fixture
def native_case(tmp_path):
    lab = NativeFailureLab(tmp_path)
    root, signer = key(), key()
    life, scope = lifecycle_event(root, signer, root)
    publication = lab.publication()
    assert publication.evidence_fingerprint is not None
    assert publication.bundle_id is not None
    subject = temporal.TemporalSubject(
        scope.namespace,
        scope.asset_kind,
        lab.publication_id,
        publication.bundle_id,
        publication.evidence_fingerprint,
    )
    record = declaration(signer, target=subject, lifecycle_tip=temporal.sha(life))
    args = dict(
        publication_id=lab.publication_id,
        expected_publication_evidence_fingerprint=publication.evidence_fingerprint,
        lifecycle_records=(life,),
        expected_lifecycle_record_sha256s=(temporal.sha(life),),
        root_public_key=public(root),
        expected_root_key_sha256=temporal.sha(public(root)),
        scope=scope,
        declarations=(record,),
        expected_declaration_sha256s=(temporal.sha(record),),
        expected_declaration_tip_sha256=temporal.sha(record),
        support_blobs=(SUPPORT,),
        request=temporal.TemporalRequest(T, T),
    )
    return lab, root, signer, subject, args


def run_case(case, **changes):
    lab, _, _, _, base = case
    args = base | changes
    with lab.opened("publications") as (source,):
        return assess_native_publication_temporal(source, **args)


def declaration_changes(case, records):
    return dict(
        declarations=tuple(records),
        expected_declaration_sha256s=tuple(temporal.sha(x) for x in records),
        expected_declaration_tip_sha256=temporal.sha(records[-1]),
    )


def test_matched_signed_times_still_reproduce_actual_research_decision_refusal(native_case):
    value = run_case(native_case)
    assert value.status == "refused_existing_research_contract"
    assert value.publication_snapshot_rechecked
    assert value.decision_refusal_reproduced
    assert value.temporal_evaluation is not None
    assert value.temporal_evaluation.declared_time_constraints_satisfied
    assert value.temporal_receipt is not None and value.admission_receipt is not None
    assert "AVAILABILITY_EVIDENCE_UNKNOWN" in value.reason_codes
    assert "ECONOMIC_VALIDITY_EVIDENCE_UNKNOWN" in value.reason_codes
    assert "CANONICAL_CONTRACT_IDENTITY_UNKNOWN" in value.reason_codes
    assert not value.independent_time_evidence_verified
    assert not value.availability_evidence_verified
    assert not value.economic_validity_verified
    assert not value.root_authority_authenticated
    assert not value.decision_eligibility_asserted
    assert not value.source_current_checked
    assert not value.atomic_cross_database_snapshot_asserted
    assert (
        replay_admission_receipt(
            encode_admission_receipt(value.admission_receipt),
            expected_receipt_id=value.admission_receipt.receipt_id,
        )
        == value.admission_receipt
    )
    assert (
        temporal.replay_temporal_receipt(
            value.temporal_receipt,
            expected_receipt_sha256=temporal.sha(value.temporal_receipt),
        )
        == value.temporal_evaluation
    )


def test_exact_reviewed_publication_pin_is_not_refreshed(native_case):
    value = run_case(native_case, expected_publication_evidence_fingerprint="0" * 64)
    assert value.status == "review_required"
    assert value.reason_codes == ("EXACT_REVIEWED_PUBLICATION_NOT_VERIFIED",)
    assert value.temporal_evaluation is None
    assert not value.decision_refusal_reproduced


@pytest.mark.parametrize(
    "kind",
    ["unknown", "future", "expired", "withdrawn"],
    ids=["unknown", "future", "expired", "withdrawn"],
)
def test_negative_declared_time_evidence_does_not_become_decision_eligible(native_case, kind):
    _, _, signer, subject, args = native_case
    changes: dict[str, object] = dict(declared_available_at=None)
    if kind == "future":
        changes = dict(declared_available_at=temporal.clock(T + timedelta(seconds=1)))
    elif kind == "expired":
        changes = dict(
            declared_economic_from=temporal.clock(T - timedelta(hours=1)),
            declared_economic_until=temporal.clock(T),
        )
    elif kind == "withdrawn":
        changes = dict(statement_kind="WITHDRAW")
    raw = declaration(
        signer,
        target=subject,
        lifecycle_tip=args["expected_lifecycle_record_sha256s"][-1],
        **changes,
    )
    value = run_case(native_case, **declaration_changes(native_case, (raw,)))
    assert value.status == "refused_existing_research_contract"
    assert value.temporal_evaluation is not None
    assert not value.temporal_evaluation.declared_time_constraints_satisfied
    assert not value.decision_eligibility_asserted


def test_rotated_old_signer_refused_until_exact_new_revision_is_supplied(native_case):
    _, root, signer, subject, args = native_case
    next_key = key()
    second, _scope = lifecycle_event(
        signer,
        next_key,
        root,
        sequence=2,
        predecessor=args["expected_lifecycle_record_sha256s"][-1],
    )
    chain_changes = dict(
        lifecycle_records=args["lifecycle_records"] + (second,),
        expected_lifecycle_record_sha256s=args["expected_lifecycle_record_sha256s"]
        + (temporal.sha(second),),
    )
    refused = run_case(native_case, **chain_changes)
    assert refused.reason_codes == ("FINAL_DECLARATION_SIGNER_RETIRED_IN_SUPPLIED_CHAIN",)
    assert refused.temporal_evaluation is None
    original = args["declarations"][0]
    revised = declaration(
        next_key,
        target=subject,
        sequence=2,
        predecessor=temporal.sha(original),
        lifecycle_tip=temporal.sha(second),
    )
    value = run_case(
        native_case, **chain_changes, **declaration_changes(native_case, (original, revised))
    )
    assert value.status == "refused_existing_research_contract"
    assert value.temporal_evaluation is not None
    assert value.temporal_evaluation.declared_time_constraints_satisfied
    assert not value.availability_evidence_verified


def test_full_supplied_lifecycle_revocation_has_precedence(native_case):
    _, root, signer, _, args = native_case
    terminal, _scope = lifecycle_event(
        signer,
        None,
        root,
        sequence=2,
        predecessor=args["expected_lifecycle_record_sha256s"][-1],
    )
    value = run_case(
        native_case,
        lifecycle_records=args["lifecycle_records"] + (terminal,),
        expected_lifecycle_record_sha256s=args["expected_lifecycle_record_sha256s"]
        + (temporal.sha(terminal),),
    )
    assert value.reason_codes == ("SUPPLIED_LIFECYCLE_TIP_REVOKED",)
    assert value.admission_receipt is None
    assert not value.authorized_revocation_asserted


def test_subject_evidence_drift_requires_new_review_not_auto_rebinding(native_case):
    lab, _, _, _, _args = native_case
    retained = run_case(native_case).temporal_receipt
    assert retained is not None
    with lab.opened("publications", writable=True) as (source,):
        records = table(source, "gold", "quote_bundle_publications")
        source.execute(f"UPDATE {records} SET published_at=published_at + INTERVAL '1 second'")
    value = run_case(native_case)
    assert value.reason_codes == ("EXACT_REVIEWED_PUBLICATION_NOT_VERIFIED",)
    new_pin = lab.publication().evidence_fingerprint
    assert new_pin is not None
    with pytest.raises(temporal.TemporalEvidenceRejected, match="SUBJECT_OR_CAUSAL_CHAIN_MISMATCH"):
        run_case(native_case, expected_publication_evidence_fingerprint=new_pin)
    # Frozen declaration replay does not repair/revalidate changed publication evidence.
    assert temporal.replay_temporal_receipt(
        retained,
        expected_receipt_sha256=temporal.sha(retained),
    ).declared_time_constraints_satisfied


def test_changed_support_and_unreviewed_lifecycle_prefix_have_no_fallback(native_case):
    with pytest.raises(temporal.TemporalEvidenceRejected, match="EXACT_SUPPORT_BYTES_REQUIRED"):
        run_case(native_case, support_blobs=(SUPPORT + b"changed",))
    _, _, signer, subject, _ = native_case
    raw = declaration(signer, target=subject, lifecycle_tip="0" * 64)
    value = run_case(native_case, **declaration_changes(native_case, (raw,)))
    assert value.reason_codes == ("DECLARATION_LIFECYCLE_PIN_NOT_IN_SUPPLIED_CHAIN",)
    assert value.temporal_evaluation is None


def test_actual_native_sql_failure_propagates_not_manufactured_refusal(native_case):
    lab = native_case[0]
    with lab.opened("publications", writable=True) as (source,):
        records = table(source, "gold", "quote_bundle_publications")
        source.execute(f"DROP TABLE {records}")
    with pytest.raises(duckdb.Error):
        run_case(native_case)
