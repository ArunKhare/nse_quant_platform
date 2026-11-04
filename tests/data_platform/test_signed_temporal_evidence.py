"""Real signature, revision, two-axis and complete retained-byte replay tests."""

import json
from dataclasses import replace
from datetime import timedelta, timezone

import pytest
from temporal_evidence_fixture import SUPPORT, T, arguments, declaration, key

from nse_quant.data_platform import signed_temporal_evidence as api


def test_real_signatures_match_claims_without_independent_time_proof():
    private = key()
    raw = declaration(private)
    args = arguments((raw,), (private,))
    result = api.evaluate_temporal_declarations(**args)
    assert result.declared_time_constraints_satisfied
    assert result.signed_declaration_constraints_satisfied
    assert result.status == "matched_supplied_declarations"
    for name in (
        "independent_time_evidence_verified",
        "availability_evidence_verified",
        "economic_validity_verified",
        "issuer_authority_authenticated",
        "history_completeness_verified",
        "authorized_revocation_asserted",
        "identity_verified",
        "historical_validity_asserted",
        "decision_eligibility_asserted",
    ):
        assert getattr(result, name) is False
    retained = api.encode_temporal_receipt(**args)
    replayed = api.replay_temporal_receipt(retained, expected_receipt_sha256=api.sha(retained))
    assert replayed == result


@pytest.mark.parametrize(
    "axis,offset,reason",
    [
        ("knowledge_cutoff", -1, "DECLARED_AVAILABILITY_AFTER_KNOWLEDGE_CUTOFF"),
        ("economic_at", -1, "ECONOMIC_AT_BEFORE_DECLARED_INTERVAL"),
        ("economic_at", 3600000000, "ECONOMIC_AT_AT_OR_AFTER_DECLARED_INTERVAL_END"),
    ],
    ids=["availability", "before-economic", "economic-end"],
)
def test_independent_axes_and_half_open_boundaries(axis, offset, reason):
    private = key()
    request = replace(api.TemporalRequest(T, T), **{axis: T + timedelta(microseconds=offset)})
    result = api.evaluate_temporal_declarations(
        **arguments((declaration(private),), (private,), request=request),
    )
    assert reason in result.reason_codes
    assert not result.declared_time_constraints_satisfied


def test_request_timezones_normalize_without_ordering_the_two_axes():
    private = key()
    args = arguments((declaration(private),), (private,))
    first = api.evaluate_temporal_declarations(**args)
    local = T.astimezone(timezone(timedelta(hours=5, minutes=30)))
    args["request"] = api.TemporalRequest(local, local)
    assert api.evaluate_temporal_declarations(**args) == first
    args["request"] = api.TemporalRequest(T + timedelta(days=1), T)
    later_knowledge = api.evaluate_temporal_declarations(**args)
    assert later_knowledge.declared_time_constraints_satisfied
    assert later_knowledge.evidence_fingerprint != first.evidence_fingerprint


@pytest.mark.parametrize(
    "field",
    ["declared_available_at", "declared_economic_from", "declared_economic_until"],
    ids=["availability", "from", "until"],
)
def test_unknown_stays_unknown_not_receipt_clock_or_infinity(field):
    private = key()
    raw = declaration(private, **{field: None})
    result = api.evaluate_temporal_declarations(**arguments((raw,), (private,)))
    assert result.reason_codes == ("DECLARED_AVAILABILITY_OR_ECONOMIC_INTERVAL_UNKNOWN",)
    assert not result.declared_time_constraints_satisfied
    assert not result.availability_evidence_verified


@pytest.mark.parametrize("kind", ["DISPUTE", "WITHDRAW"], ids=["dispute", "withdraw"])
def test_negative_revision_is_not_repaired_by_later_assertion(kind):
    private = key()
    first = declaration(private, statement_kind=kind)
    later = declaration(private, sequence=2, predecessor=api.sha(first))
    result = api.evaluate_temporal_declarations(**arguments((first, later), (private, private)))
    assert result.reason_codes == ("SUPPLIED_SERIES_DISPUTED_OR_WITHDRAWN_NO_REACTIVATION",)
    assert not result.declared_time_constraints_satisfied


@pytest.mark.parametrize(
    "mode",
    ["gap", "fork", "wrong-prev", "tip", "subject"],
    ids=["gap", "fork", "wrong-prev", "tip", "subject"],
)
def test_entire_revision_chain_and_exact_subject_pins(mode):
    private = key()
    first = declaration(private)
    later = declaration(private, sequence=2, predecessor=api.sha(first))
    if mode == "gap":
        later = declaration(private, sequence=3, predecessor=api.sha(first))
    elif mode == "fork":
        later = declaration(private)
    elif mode == "wrong-prev":
        later = declaration(private, sequence=2, predecessor="0" * 64)
    args = arguments((first, later), (private, private))
    if mode == "tip":
        args["expected_tip_sha256"] = api.sha(first)
    elif mode == "subject":
        args["subject"] = replace(args["subject"], publication_id="0" * 64)
    with pytest.raises(api.TemporalEvidenceRejected):
        api.evaluate_temporal_declarations(**args)


def test_invalid_later_signature_is_checked_before_any_availability_filter():
    private = key()
    first = declaration(private, declared_available_at=api.clock(T + timedelta(days=1)))
    later = json.loads(declaration(private, sequence=2, predecessor=api.sha(first)))
    later["signature_hex"] = "00" * 64
    changed = api.canonical(later)
    with pytest.raises(api.TemporalEvidenceRejected, match="SIGNATURE_INVALID"):
        api.evaluate_temporal_declarations(**arguments((first, changed), (private, private)))


@pytest.mark.parametrize(
    "change",
    [
        dict(declared_economic_until=api.clock(T)),
        dict(declared_available_at="2026-01-01T05:30:00+05:30"),
        dict(declared_available_at="2026-01-01T00:00:00"),
    ],
    ids=["empty-interval", "noncanonical-offset", "naive"],
)
def test_invalid_declared_clock_or_interval_no_normalization_salvage(change):
    private = key()
    raw = declaration(private, **change)
    with pytest.raises(api.TemporalEvidenceRejected):
        api.evaluate_temporal_declarations(**arguments((raw,), (private,)))


def test_support_hash_integrity_is_required_but_never_authenticates_source():
    private = key()
    args = arguments((declaration(private),), (private,))
    args["support_blobs"] = (SUPPORT + b"changed",)
    with pytest.raises(api.TemporalEvidenceRejected, match="EXACT_SUPPORT_BYTES_REQUIRED"):
        api.evaluate_temporal_declarations(**args)


@pytest.mark.parametrize(
    "mode",
    ["whitespace", "duplicate", "nonfinite", "mutable"],
    ids=["whitespace", "duplicate", "nonfinite", "mutable"],
)
def test_strict_original_signed_bytes(mode):
    private = key()
    raw = declaration(private)
    args = arguments((raw,), (private,))
    if mode == "mutable":
        args["records"] = (bytearray(raw),)
    else:
        if mode == "whitespace":
            raw += b" "
        elif mode == "duplicate":
            raw = raw.replace(b"{", b'{"signature_hex":"bad",', 1)
        else:
            raw = raw.replace(b"{", b'{"extra":NaN,', 1)
        args = arguments((raw,), (private,))
    with pytest.raises(api.TemporalEvidenceRejected):
        api.evaluate_temporal_declarations(**args)


def test_rehashed_tampered_result_cannot_promote_independent_evidence():
    private = key()
    raw = api.encode_temporal_receipt(**arguments((declaration(private),), (private,)))
    value = json.loads(raw)
    value["result"]["availability_evidence_verified"] = True
    changed = api.canonical(value)
    with pytest.raises(api.TemporalEvidenceRejected, match="COMPLETE_RECEIPT_REPLAY_MISMATCH"):
        api.replay_temporal_receipt(changed, expected_receipt_sha256=api.sha(changed))
    with pytest.raises(api.TemporalEvidenceRejected, match="PIN_MISMATCH"):
        api.replay_temporal_receipt(raw, expected_receipt_sha256="0" * 64)


def test_actual_resource_bounds_without_weakened_limits():
    private = key()
    raw = declaration(private)
    args = arguments((raw,) * 17, (private,) * 17)
    with pytest.raises(api.TemporalEvidenceRejected, match="BOUNDED_INPUTS_REQUIRED"):
        api.evaluate_temporal_declarations(**args)
    args = arguments((b"x" * api.MAX_RECORD_BYTES,) * 15, (private,) * 15)
    with pytest.raises(api.TemporalEvidenceRejected, match="RECORD_AGGREGATE_BOUND"):
        api.evaluate_temporal_declarations(**args)
    args = arguments((raw,), (private,))
    args["support_blobs"] = (b"x" * api.MAX_SUPPORT_BYTES,) * 5
    with pytest.raises(api.TemporalEvidenceRejected, match="SUPPORT_AGGREGATE_BOUND"):
        api.evaluate_temporal_declarations(**args)
