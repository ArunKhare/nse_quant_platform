"""Pure frozen-summary policy tests; NOT publication/source attestation or E2E."""

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime

import pytest

from nse_quant.data_platform import legacy_market_publication as publication
from nse_quant.data_platform import legacy_market_publication_admission as policy
from nse_quant.data_platform.publication_admission import (
    ARCHIVED_RESEARCH,
    POINT_IN_TIME,
    AdmissionRequest,
    _request_dict,
)


@pytest.fixture
def frozen():
    gold = "a" * 64
    bundle = "b" * 64
    clock = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    return dict(
        definition=publication._hash(policy.DEFINITION),
        request=_request_dict(AdmissionRequest(ARCHIVED_RESEARCH)),
        source=dict(
            publication_id=publication.publication_id(gold, bundle),
            recording_fingerprint="c" * 64,
            bundle_id=bundle,
            gold_build_id=gold,
            row_count=1001,
            purpose=publication.PURPOSE,
            clock_semantics=publication.CLOCK,
            publication_recorded_at=clock,
            origin_audit_success_recorded_at=clock,
            research_publication_verified=True,
            current_source_checked=False,
            decision_eligibility_asserted=False,
            availability_verified=False,
            economic_validity_verified=False,
            canonical_contract_id=None,
        ),
    )


def evaluate(value):
    return policy._evaluate(publication._canonical(value))


def test_summary_replay_is_not_authentication(frozen):
    original = evaluate(frozen)
    assert original.research_analysis_permitted
    frozen["source"]["recording_fingerprint"] = "d" * 64
    changed = evaluate(frozen)
    assert changed.research_analysis_permitted  # Offline declaration, NOT native source proof.
    assert changed.receipt_id != original.receipt_id
    assert not changed.replay_authenticity_asserted
    assert not changed.source_current_checked


def test_point_in_time_refused_even_with_matching_record_clocks(frozen):
    at = datetime(2026, 1, 1, tzinfo=UTC)
    frozen["request"] = _request_dict(AdmissionRequest(POINT_IN_TIME, at, at))
    receipt = evaluate(frozen)
    assert receipt.status == "REJECTED"
    assert not receipt.research_analysis_permitted
    assert not receipt.decision_eligibility_asserted
    assert "RECORD_CLOCKS_ARE_NOT_AVAILABILITY_PROOF" in receipt.reason_codes
    raw = policy.encode_legacy_admission(receipt)
    assert policy.replay_legacy_admission(raw, expected_receipt_id=receipt.receipt_id) == receipt


@pytest.mark.parametrize(
    "key,value",
    [
        ("purpose", "POINT_IN_TIME_DECISION"),
        ("research_publication_verified", False),
        ("availability_verified", True),
        ("economic_validity_verified", True),
        ("decision_eligibility_asserted", True),
        ("canonical_contract_id", "invented"),
        ("current_source_checked", True),
        ("row_count", 0),
        ("row_count", 16001),
        ("row_count", True),
        ("publication_id", "0" * 64),
        ("recording_fingerprint", "bad"),
        ("clock_semantics", "independent"),
        ("publication_recorded_at", "2026-01-01T00:00:00"),
    ],
    ids=[
        "purpose",
        "not-verified",
        "availability",
        "economic",
        "decision",
        "identity",
        "current",
        "empty",
        "overflow",
        "bool-count",
        "publication-id",
        "recording-pin",
        "clock-semantics",
        "naive-clock",
    ],
)
def test_summary_contract_rejects_unsupported_claims(frozen, key, value):
    frozen["source"][key] = value
    with pytest.raises(ValueError):
        evaluate(frozen)


def test_receipt_claim_tampering_even_with_rehashed_bytes(frozen):
    receipt = evaluate(frozen)
    doc = asdict(receipt)
    del doc["receipt_id"]
    doc["decision_eligibility_asserted"] = True
    raw = publication._canonical(doc).encode()
    with pytest.raises(ValueError, match="RESULT"):
        policy.replay_legacy_admission(raw, expected_receipt_id=publication.bundle.gold.sha(raw))
    with pytest.raises(ValueError, match="RESULT"):
        policy.encode_legacy_admission(replace(receipt, status="ACCEPTED_DECISION"))


@pytest.mark.parametrize(
    "raw", [b"", b"[]", b"{}", b"not-json"], ids=["empty", "array", "object", "invalid-json"]
)
def test_invalid_receipt_content(raw):
    with pytest.raises(ValueError):
        policy.replay_legacy_admission(raw, expected_receipt_id=publication.bundle.gold.sha(raw))


def test_duplicate_keys_and_extra_fields_cannot_survive_canonical_replay(frozen):
    encoded = publication._canonical(frozen)
    altered = encoded[:-1] + ',"definition":"bad"}'
    with pytest.raises(ValueError):
        policy._evaluate(altered)
    frozen["extra"] = True
    with pytest.raises(ValueError):
        evaluate(frozen)


def test_policy_byte_bounds_before_parse():
    with pytest.raises(ValueError, match="BYTE_BOUND"):
        policy._evaluate("x" * (policy.MAX_BYTES + 1))
    raw = b"x" * (policy.MAX_BYTES + 1)
    with pytest.raises(ValueError, match="BYTE_BOUND"):
        policy.replay_legacy_admission(raw, expected_receipt_id=publication.bundle.gold.sha(raw))


def test_request_axes_are_not_optional_or_naively_utc():
    with pytest.raises(ValueError):
        AdmissionRequest(POINT_IN_TIME)
    with pytest.raises(ValueError):
        AdmissionRequest(ARCHIVED_RESEARCH, datetime.now(UTC))
    with pytest.raises(ValueError):
        AdmissionRequest(POINT_IN_TIME, datetime(2026, 1, 1), datetime.now(UTC))


def test_exact_receipt_roundtrip_and_checksum(frozen):
    receipt = evaluate(frozen)
    raw = policy.encode_legacy_admission(receipt)
    assert json.loads(raw)["status"] == "ACCEPTED_RESEARCH_ONLY"
    assert policy.replay_legacy_admission(raw, expected_receipt_id=receipt.receipt_id) == receipt
    with pytest.raises(ValueError, match="CHECKSUM"):
        policy.replay_legacy_admission(raw, expected_receipt_id="0" * 64)
