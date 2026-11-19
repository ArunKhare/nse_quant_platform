"""Pure summary-only policy replay; never native publication/source authentication."""

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime

import pytest

from nse_quant.data_platform import legacy_window_admission as policy
from nse_quant.data_platform import legacy_window_publication as publication
from nse_quant.data_platform.publication_admission import (
    ARCHIVED_RESEARCH,
    POINT_IN_TIME,
    AdmissionRequest,
    _request_dict,
)


@pytest.fixture
def frozen():
    clock = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    return dict(
        definition=publication.native._hash(policy.DEFINITION),
        request=_request_dict(AdmissionRequest(ARCHIVED_RESEARCH)),
        source=dict(
            publication_id=publication.publication_id("a" * 64, "b" * 64),
            recording_fingerprint="c" * 64,
            bundle_id="b" * 64,
            window_build_id="a" * 64,
            policy=dict(window_returns=2, cadence_microseconds=60000000),
            row_count=1001,
            purpose=publication.PURPOSE,
            publication_recorded_at=clock,
            origin_audit_success_recorded_at=clock,
            clock_semantics=publication.CLOCK,
            research_publication_verified=True,
            current_source_checked=False,
            decision_eligibility_asserted=False,
            availability_verified=False,
            economic_validity_verified=False,
            authoritative_market_coverage_verified=False,
            canonical_contract_id=None,
        ),
    )


def evaluate(value):
    return policy._evaluate(publication.native._canonical(value))


def test_exact_receipt_and_offline_fingerprint_is_only_a_declaration(frozen):
    receipt = evaluate(frozen)
    assert receipt.research_analysis_permitted
    raw = policy.encode_window_admission(receipt)
    assert policy.replay_window_admission(raw, expected_receipt_id=receipt.receipt_id) == receipt
    frozen["source"]["recording_fingerprint"] = "d" * 64
    other = evaluate(frozen)
    assert other.research_analysis_permitted
    assert other.receipt_id != receipt.receipt_id
    assert not other.research_analysis_authorized
    assert not other.replay_authenticity_asserted


def test_point_in_time_always_refused_even_matching_record_clocks(frozen):
    at = datetime(2026, 1, 1, tzinfo=UTC)
    frozen["request"] = _request_dict(AdmissionRequest(POINT_IN_TIME, at, at))
    result = evaluate(frozen)
    assert result.policy_status == "REJECTED"
    assert not result.research_analysis_permitted
    assert not result.decision_eligibility_asserted


@pytest.mark.parametrize(
    "key,value",
    [
        ("purpose", "POINT_IN_TIME_DECISION"),
        ("research_publication_verified", False),
        ("availability_verified", True),
        ("economic_validity_verified", True),
        ("authoritative_market_coverage_verified", True),
        ("decision_eligibility_asserted", True),
        ("canonical_contract_id", "invented"),
        ("current_source_checked", True),
        ("row_count", True),
        ("row_count", 0),
        ("row_count", 16001),
        ("recording_fingerprint", "bad"),
        ("publication_id", "0" * 64),
        ("policy", dict(window_returns=1, cadence_microseconds=60000000)),
        ("publication_recorded_at", "2026-01-01T00:00:00"),
    ],
    ids=[
        "purpose",
        "unverified",
        "availability",
        "economic",
        "coverage",
        "decision",
        "identity",
        "current",
        "bool-count",
        "empty",
        "overflow",
        "pin",
        "publication-id",
        "policy",
        "naive",
    ],
)
def test_false_positive_claims_and_invalid_summary_reject(frozen, key, value):
    frozen["source"][key] = value
    with pytest.raises(ValueError):
        evaluate(frozen)


def test_rehashed_receipt_cannot_promote_result(frozen):
    receipt = evaluate(frozen)
    doc = asdict(receipt)
    del doc["receipt_id"]
    doc["decision_eligibility_asserted"] = True
    raw = publication.native._canonical(doc).encode()
    with pytest.raises(ValueError, match="RESULT"):
        policy.replay_window_admission(raw, expected_receipt_id=publication.bundle.sha(raw))
    with pytest.raises(ValueError, match="RESULT"):
        policy.encode_window_admission(replace(receipt, policy_status="ACCEPTED_DECISION"))


@pytest.mark.parametrize(
    "raw", [b"", b"{}", b"[]", b"bad"], ids=["empty", "object", "array", "invalid"]
)
def test_invalid_receipt(raw):
    with pytest.raises(ValueError):
        policy.replay_window_admission(raw, expected_receipt_id=publication.bundle.sha(raw))


def test_bounds_before_decode_and_extra_schema_fields(frozen):
    raw = b"x" * (policy.MAX_BYTES + 1)
    with pytest.raises(ValueError, match="BYTE_BOUND"):
        policy.replay_window_admission(raw, expected_receipt_id=publication.bundle.sha(raw))
    frozen["extra"] = True
    with pytest.raises(ValueError):
        evaluate(frozen)


def test_duplicate_keys_and_exact_canonical_contract(frozen):
    raw = publication.native._canonical(frozen)
    with pytest.raises(ValueError):
        policy._evaluate(raw[:-1] + ',"definition":"bad"}')
    assert json.loads(raw)["source"]["purpose"] == "RESEARCH_ONLY"
