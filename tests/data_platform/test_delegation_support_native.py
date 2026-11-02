"""Actual native reference/JSONL/audit/delegation composition on disposable fixtures."""

import hashlib
from dataclasses import asdict, replace

import pytest
from test_checkpoint_native_revalidation import checkpoint_case as checkpoint_case
from test_delegation_native_reader import declarations
from test_identity_statement_reader_native import source_claim as source_claim
from test_signature_receipt_reader_native import proof_store as proof_store

from nse_quant.data_platform import bronze_jsonl_recompute as codec
from nse_quant.data_platform import bronze_jsonl_support_reader as jsonl
from nse_quant.data_platform import delegation_native_reader as native
from nse_quant.data_platform import delegation_support_reader as reader
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze_support_reader import BronzeSupportPin
from nse_quant.data_platform.delegation_review import EXTERNAL, INTERNAL


def supporting_inputs(args, *, multiple=False, bad_fragment=False):
    request = args["request"]
    support = BronzeSupportPin(
        request.bronze_capture_event_id,
        request.bronze_envelope_hash,
        request.evidence_payload_hash,
        request.evidence_byte_start,
        request.evidence_byte_end,
        "0" * 64 if bad_fragment else request.evidence_fragment_sha256,
    )
    supports = [support]
    if multiple:
        supports.append(
            replace(
                support,
                byte_end=len(args["payload"]),
                fragment_sha256=hashlib.sha256(args["payload"]).hexdigest(),
            )
        )
    sources = tuple(
        reader.DelegationReferenceSource(
            args["bronze"],
            pin,
            args["original_plan"],
            args["expected_plan_sha256"],
        )
        for pin in supports
    )
    signed = declarations(args, evidence_refs=[asdict(pin) for pin in supports])
    return dict(declarations=signed, expected_model=INTERNAL, reference_sources=sources)


def test_all_exact_signed_refs_are_storage_linked_not_authority(checkpoint_case):
    args, _, _, _, _ = checkpoint_case()
    supplied = supporting_inputs(args, multiple=True)
    value = reader.inspect_delegation_reference_support(**args, **supplied)
    assert value.all_signed_reference_storage_verified
    assert len(value.support_before) == len(value.support_after) == 2
    assert value.coverage.exact_coverage
    assert value.native_before.internal_review_evidence_bound
    assert not value.native_before.supporting_bronze_refs_checked
    assert not value.review.observations[0].supporting_bronze_refs_checked
    assert not value.reference_content_semantics_verified
    assert not value.source_acquisition_authenticity_asserted
    assert not value.reviewer_identities_authenticated
    assert not value.internal_authorization_asserted
    assert not value.policy_authority_authenticated
    assert not value.external_issuer_authority_verified
    assert not value.namespace_authority_verified
    assert not value.issuer_authenticated
    assert not value.identity_verified
    assert not value.authorized_revocation_asserted
    assert not value.decision_eligibility_asserted
    assert not value.atomic_cross_database_snapshot_asserted
    assert value.canonical_underlying_id is None


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("missing", "SIGNED_REFERENCE_SOURCE_MISSING"),
        ("extra", "UNSIGNED_EXTRA_REFERENCE_SOURCE"),
        ("duplicate", "AMBIGUOUS_DUPLICATE_REFERENCE_SOURCE"),
    ],
)
def test_bad_coverage_stops_before_any_source_reads(checkpoint_case, monkeypatch, mode, reason):
    args, _, _, _, _ = checkpoint_case()
    supplied = supporting_inputs(args)
    item = supplied["reference_sources"][0]
    if mode == "missing":
        supplied["reference_sources"] = ()
    elif mode == "duplicate":
        supplied["reference_sources"] = (item, item)
    else:
        extra = replace(item, support=replace(item.support, byte_end=item.support.byte_end - 1))
        supplied["reference_sources"] = (item, extra)

    def forbidden(*positional, **keywords):
        raise AssertionError("Incomplete coverage reached source I/O")

    monkeypatch.setattr(jsonl, "inspect_jsonl_bronze_support", forbidden)
    value = reader.inspect_delegation_reference_support(**args, **supplied)
    assert reason in value.reason_codes
    assert not value.all_signed_reference_storage_verified
    assert value.support_before == ()
    assert value.native_before is None


def test_wrong_fragment_is_not_healed_by_valid_signatures(checkpoint_case):
    args, _, _, _, _ = checkpoint_case()
    value = reader.inspect_delegation_reference_support(
        **args,
        **supporting_inputs(args, bad_fragment=True),
    )
    assert value.review.internal_review_constraints_satisfied
    assert value.reason_codes == ("SIGNED_REFERENCE_SUPPORT_NOT_COMPLETE_BEFORE",)
    assert not value.all_signed_reference_storage_verified
    assert value.native_before is None


def test_actual_source_retry_between_native_reads_blocks(checkpoint_case, monkeypatch):
    args, claim, _, _, _ = checkpoint_case()
    supplied = supporting_inputs(args)
    real = native.inspect_delegation_native_binding
    calls = 0

    def observe(*positional, **keywords):
        nonlocal calls
        value = real(*positional, **keywords)
        calls += 1
        if calls == 1:
            claim[6]()
        return value

    monkeypatch.setattr(native, "inspect_delegation_native_binding", observe)
    value = reader.inspect_delegation_reference_support(**args, **supplied)
    assert "SIGNED_REFERENCE_SUPPORT_CHANGED_OR_INCOMPLETE_AFTER" in value.reason_codes
    assert not value.all_signed_reference_storage_verified
    assert value.support_before != value.support_after


def test_incomplete_source_audit_blocks_before_native(checkpoint_case):
    args, _, _, _, _ = checkpoint_case()
    supplied = supporting_inputs(args)
    AuditLedger(args["bronze"]).plan_job(
        command_name=codec.COMMAND,
        actor_id="test",
        code_revision="synthetic-test",
        scope_ref="sha256:" + args["expected_plan_sha256"],
        config_hash=codec.CONFIG_HASH,
    )
    value = reader.inspect_delegation_reference_support(**args, **supplied)
    assert not value.all_signed_reference_storage_verified
    assert value.support_before[0].status == "review_required"
    assert value.native_before is None


def test_external_claim_never_upgrades_after_source_matching(checkpoint_case):
    args, _, _, _, _ = checkpoint_case()
    supplied = supporting_inputs(args)
    refs = [asdict(item.support) for item in supplied["reference_sources"]]
    supplied.update(
        declarations=declarations(args, EXTERNAL, evidence_refs=refs), expected_model=EXTERNAL
    )
    value = reader.inspect_delegation_reference_support(**args, **supplied)
    assert not value.all_signed_reference_storage_verified
    assert value.support_before == ()
    assert value.native_before is None
    assert not value.external_issuer_authority_verified


def test_source_failure_propagates_without_fabricating_rejection(checkpoint_case, monkeypatch):
    args, _, _, _, _ = checkpoint_case()

    def fail(*positional, **keywords):
        raise RuntimeError("SYNTHETIC_SOURCE_FAILURE")

    monkeypatch.setattr(jsonl, "inspect_jsonl_bronze_support", fail)
    with pytest.raises(RuntimeError, match="SYNTHETIC_SOURCE_FAILURE"):
        reader.inspect_delegation_reference_support(**args, **supporting_inputs(args))
