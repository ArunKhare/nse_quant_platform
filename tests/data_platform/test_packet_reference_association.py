"""Association boundary tests; reader verification remains independently tested."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from nse_quant.data_platform import packet_reference_association as service
from nse_quant.data_platform.kite_decoder import DecodedFrame, Packet
from nse_quant.data_platform.kite_frame_reader import READER_VERSION, KiteFrameEvidence
from nse_quant.data_platform.native_reference_reader import (
    NativeReferenceLookup,
    NativeReferenceRowPin,
)
from nse_quant.data_platform.reference_supersession import RESOLVER_VERSION

FRAME = "a" * 64
REFERENCE = "b" * 64
FINGERPRINT = "c" * 64
ROW_HASH = "d" * 64


def packet(ordinal=0, token=257):
    return Packet(
        ordinal, 2, 4, 8, token, 1, 100, "ltp", (("last_price_raw", 12345),), None, None, ()
    )


def frame():
    return KiteFrameEvidence(
        READER_VERSION,
        FRAME,
        "verified",
        "SOURCE_RECOMPUTED",
        evidence_fingerprint=FINGERPRINT,
        decoded=DecodedFrame("quote_ticks", "DECODED", (packet(),)),
    )


def lookup():
    return NativeReferenceLookup(
        RESOLVER_VERSION,
        REFERENCE,
        257,
        "matched",
        "UNIQUE_TOKEN_ROW",
        (REFERENCE,),
        (NativeReferenceRowPin(REFERENCE, 0, ROW_HASH),),
    )


@pytest.fixture
def setup(monkeypatch):
    state = {"frame": frame(), "lookup": lookup(), "calls": []}
    bronze, frames, references = object(), object(), object()

    def read(b, s, *, revision_id):
        assert b is bronze and s is frames
        assert revision_id == FRAME
        state["calls"].append("frame")
        return state["frame"]

    def resolve(b, s, *, assessment_revision_id, instrument_token):
        assert b is bronze and s is references
        assert assessment_revision_id == REFERENCE
        assert instrument_token == state["frame"].decoded.packets[0].instrument_token
        state["calls"].append("reference")
        return state["lookup"]

    monkeypatch.setattr(service, "read_kite_frame", read)
    monkeypatch.setattr(service, "lookup_native_reference", resolve)

    def run(**kwargs):
        args = {
            "frame_revision_id": FRAME,
            "packet_ordinal": 0,
            "reference_assessment_revision_id": REFERENCE,
        }
        args.update(kwargs)
        return service.associate_packet_reference(bronze, frames, references, **args)

    return state, run


def test_associated_preserves_evidence_and_no_identity_claims(setup):
    state, run = setup
    result = run()
    assert result.status == "associated"
    assert result.packet == packet()
    assert result.reference_lookup == lookup()
    assert result.frame_evidence_fingerprint == FINGERPRINT
    assert result.canonical_contract_id is None
    assert not result.publication_asserted
    assert not result.historical_validity_asserted
    assert not result.decision_eligibility_asserted
    assert result.packet.exchange_event_time is None
    assert state["calls"] == ["frame", "reference"]
    assert run() == result


@pytest.mark.parametrize("ordinal", [-1, 4096, True, 0.5])
def test_invalid_ordinal_before_readers(setup, ordinal):
    state, run = setup
    with pytest.raises(ValueError, match="INVALID_PACKET_ORDINAL"):
        run(packet_ordinal=ordinal)
    assert state["calls"] == []


@pytest.mark.parametrize("field", ["frame_revision_id", "reference_assessment_revision_id"])
def test_invalid_pin_before_readers(setup, field):
    state, run = setup
    with pytest.raises(ValueError, match="EXACT_FRAME_AND_REFERENCE_PINS_REQUIRED"):
        run(**{field: "A" * 64})
    assert state["calls"] == []


@pytest.mark.parametrize("reason", ["BRONZE_RECEIPT_CONFLICT", "NORMALIZATION_AUDIT_NOT_VERIFIED"])
def test_blocked_frame_short_circuits(setup, reason):
    state, run = setup
    state["frame"] = replace(frame(), status="blocked", reason_code=reason, decoded=None)
    assert run().reason_code == "FRAME_" + reason
    assert state["calls"] == ["frame"]


@pytest.mark.parametrize(
    "classification", ["heartbeat_control", "quarantine", "unsupported", "text_notification"]
)
def test_nonquote_frame_short_circuits(setup, classification):
    state, run = setup
    state["frame"] = replace(frame(), decoded=DecodedFrame(classification, "OTHER"))
    assert run().reason_code == "FRAME_NOT_QUOTE_TICKS"
    assert state["calls"] == ["frame"]


def test_out_of_frame_ordinal(setup):
    state, run = setup
    assert run(packet_ordinal=1).reason_code == "PACKET_NOT_IN_PINNED_FRAME"
    assert state["calls"] == ["frame"]


@pytest.mark.parametrize("token", [0, -1, 2**32, True])
def test_bad_packet_token(setup, token):
    state, run = setup
    state["frame"] = replace(
        frame(), decoded=DecodedFrame("quote_ticks", "DECODED", (packet(token=token),))
    )
    assert run().reason_code == "INVALID_PACKET_PROVIDER_TOKEN"
    assert state["calls"] == ["frame"]


@pytest.mark.parametrize(
    "status,reason,candidates",
    [
        (
            "ambiguous",
            "MULTIPLE_TOKEN_ROWS",
            (
                NativeReferenceRowPin(REFERENCE, 0, ROW_HASH),
                NativeReferenceRowPin(REFERENCE, 1, ROW_HASH),
            ),
        ),
        ("unresolved", "TOKEN_NOT_IN_PINNED_ASSESSMENT", ()),
        ("blocked", "ASSESSMENT_SUPERSEDED", ()),
        ("blocked", "SOURCE_RECEIPT_CONFLICT", ()),
    ],
)
def test_reference_outcomes_preserved(setup, status, reason, candidates):
    state, run = setup
    state["lookup"] = replace(lookup(), status=status, reason_code=reason, candidates=candidates)
    result = run()
    assert result.status == status
    assert result.reason_code == "REFERENCE_" + reason
    assert result.reference_lookup.candidates == candidates
    assert result.packet == packet()


@pytest.mark.parametrize(
    "changes",
    [
        {"assessment_revision_id": "e" * 64},
        {"instrument_token": 513},
        {"resolver_version": "unsupported"},
        {"publication_asserted": True},
        {"historical_validity_asserted": True},
        {"status": "unexpected"},
        {"evidence_mode": "TIMELESS_TOKEN_IDENTITY"},
    ],
)
def test_reference_contract_mismatch(setup, changes):
    state, run = setup
    state["lookup"] = replace(lookup(), **changes)
    result = run()
    assert result.status == "blocked"
    assert result.reference_lookup is None
    assert result.reason_code == "REFERENCE_READER_CONTRACT_MISMATCH"


@pytest.mark.parametrize(
    "candidates",
    [
        (),
        (
            NativeReferenceRowPin(REFERENCE, 0, ROW_HASH),
            NativeReferenceRowPin(REFERENCE, 1, ROW_HASH),
        ),
    ],
)
def test_match_requires_exactly_one_candidate(setup, candidates):
    state, run = setup
    state["lookup"] = replace(lookup(), candidates=candidates)
    assert run().reason_code == "REFERENCE_STATUS_CONTRACT_MISMATCH"


@pytest.mark.parametrize(
    "candidate",
    [
        NativeReferenceRowPin("e" * 64, 0, ROW_HASH),
        NativeReferenceRowPin(REFERENCE, -1, ROW_HASH),
        NativeReferenceRowPin(REFERENCE, True, ROW_HASH),
        NativeReferenceRowPin(REFERENCE, 200_000, ROW_HASH),
        NativeReferenceRowPin(REFERENCE, 0, "invalid"),
    ],
)
def test_bad_candidate_pin(setup, candidate):
    state, run = setup
    state["lookup"] = replace(lookup(), candidates=(candidate,))
    assert run().reason_code == "REFERENCE_CANDIDATE_CONTRACT_MISMATCH"


def test_duplicate_candidates_not_first_wins(setup):
    state, run = setup
    state["lookup"] = replace(
        lookup(),
        status="ambiguous",
        reason_code="MULTIPLE_TOKEN_ROWS",
        candidates=lookup().candidates * 2,
    )
    assert run().reason_code == "REFERENCE_CANDIDATE_CONTRACT_MISMATCH"


def test_active_pin_required(setup):
    state, run = setup
    state["lookup"] = replace(lookup(), active_revision_ids=("e" * 64,))
    assert run().reason_code == "REFERENCE_ACTIVE_PIN_MISMATCH"


def test_reader_exceptions_are_not_success(setup, monkeypatch):
    _, run = setup

    def fail(*args, **kwargs):
        raise RuntimeError("execution failure")

    monkeypatch.setattr(service, "lookup_native_reference", fail)
    with pytest.raises(RuntimeError, match="execution failure"):
        run()


def test_fingerprint_changes_with_source_evidence(setup):
    state, run = setup
    original = run().association_fingerprint
    state["frame"] = replace(frame(), evidence_fingerprint="e" * 64)
    assert run().association_fingerprint != original
    state["lookup"] = replace(lookup(), candidates=(NativeReferenceRowPin(REFERENCE, 0, "f" * 64),))
    assert run().association_fingerprint != original


def test_packet_times_are_not_promoted_to_validity(setup):
    state, run = setup
    p = replace(packet(), exchange_event_time=datetime(2026, 1, 1, tzinfo=UTC))
    state["frame"] = replace(frame(), decoded=DecodedFrame("quote_ticks", "DECODED", (p,)))
    result = run()
    assert result.packet.exchange_event_time == p.exchange_event_time
    assert result.historical_validity_asserted is False


@pytest.mark.parametrize(
    "changes",
    [
        {"reader_version": "unknown"},
        {"revision_id": "e" * 64},
        {"evidence_fingerprint": None},
        {"publication_asserted": True},
        {"historical_validity_asserted": True},
        {"decision_eligibility_asserted": True},
        {"decoded": None},
    ],
)
def test_frame_contract_mismatch(setup, changes):
    state, run = setup
    state["frame"] = replace(frame(), **changes)
    assert run().reason_code == "FRAME_READER_CONTRACT_MISMATCH"
    assert state["calls"] == ["frame"]


def test_packet_ordinal_contract(setup):
    state, run = setup
    state["frame"] = replace(
        frame(), decoded=DecodedFrame("quote_ticks", "DECODED", (packet(ordinal=1),))
    )
    assert run().reason_code == "PACKET_ORDINAL_MISMATCH"
    assert state["calls"] == ["frame"]


def test_repeated_calls_reverify_not_cache(setup):
    state, run = setup
    assert run().status == "associated"
    state["lookup"] = replace(
        lookup(),
        status="blocked",
        reason_code="ASSESSMENT_SUPERSEDED",
        candidates=(),
        active_revision_ids=("e" * 64,),
    )
    assert run().status == "blocked"
    assert state["calls"] == ["frame", "reference", "frame", "reference"]


def test_candidate_limit(setup):
    state, run = setup
    state["lookup"] = replace(
        lookup(),
        status="ambiguous",
        reason_code="MULTIPLE_TOKEN_ROWS",
        candidates=tuple(NativeReferenceRowPin(REFERENCE, i, ROW_HASH) for i in range(1001)),
    )
    assert run().reason_code == "REFERENCE_CANDIDATE_CONTRACT_MISMATCH"
