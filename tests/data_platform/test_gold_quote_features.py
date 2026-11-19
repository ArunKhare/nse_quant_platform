"""Exact arithmetic and feature boundary tests; no source integrity shortcuts."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import localcontext

import pytest

from nse_quant.data_platform import gold_quote_features as gold
from nse_quant.data_platform.kite_decoder import Packet
from nse_quant.data_platform.native_reference_reader import (
    NativeReferenceLookup,
    NativeReferenceRowPin,
)
from nse_quant.data_platform.packet_association_reader import (
    READER_VERSION,
    PersistedAssociationEvidence,
)
from nse_quant.data_platform.packet_reference_association import (
    ASSOCIATION_VERSION,
    PacketReferenceAssociation,
)
from nse_quant.data_platform.reference_supersession import RESOLVER_VERSION

PIN = "a" * 64


def evidence(*, segment=1, size=8, prices=None):
    raw = {"last_price_raw": 12345}
    if size in {28, 32}:
        raw.update(
            open_raw=12000, high_raw=12500, low_raw=11900, close_raw=12100, index_change_bits=0
        )
    if size == 32:
        raw["exchange_epoch_seconds"] = 0
    if size in {44, 184}:
        raw.update(
            last_quantity=10,
            average_price_raw=12200,
            volume=1000,
            buy_quantity=100,
            sell_quantity=200,
            open_raw=12000,
            high_raw=12500,
            low_raw=11900,
            close_raw=12100,
        )
    if size == 184:
        raw.update(
            last_trade_epoch_seconds=0, oi=10, oi_high=20, oi_low=5, exchange_epoch_seconds=0
        )
    if prices:
        raw.update(prices)
    divisor = 10_000_000 if segment == 3 else 10_000 if segment in {6, 12} else 100
    mode = "ltp" if size == 8 else "quote" if size in {28, 44} else "full"
    packet = Packet(
        0, 2, 4, size, 256 + segment, segment, divisor, mode, tuple(raw.items()), None, None, ()
    )
    lookup = NativeReferenceLookup(
        RESOLVER_VERSION,
        "b" * 64,
        packet.instrument_token,
        "matched",
        "UNIQUE_TOKEN_ROW",
        ("b" * 64,),
        (NativeReferenceRowPin("b" * 64, 0, "c" * 64),),
    )
    association = PacketReferenceAssociation(
        ASSOCIATION_VERSION,
        "d" * 64,
        0,
        "b" * 64,
        "associated",
        "UNIQUE_PINNED_REFERENCE_ROW",
        "e" * 64,
        packet,
        lookup,
        "f" * 64,
    )
    return PersistedAssociationEvidence(
        READER_VERSION,
        PIN,
        "verified_current",
        "SOURCE_RECOMPUTED",
        (PIN,),
        ("job1",),
        association,
        "e" * 64,
    )


def build(source):
    return gold._derive_price_candidate(source, PIN)


@pytest.mark.parametrize(
    "numerator,divisor,expected",
    [
        (12345, 100, "123.45"),
        (0, 100, "0.00"),
        (-1, 100, "-0.01"),
        (1, 10_000, "0.0001"),
        (1, 10_000_000, "0.0000001"),
        (4294967295, 100, "42949672.95"),
        (4294967295, 10_000_000, "429.4967295"),
    ],
)
def test_exact_scaling(numerator, divisor, expected):
    with localcontext() as context:
        context.prec = 1
        assert gold.exact_price_decimal(numerator, divisor) == expected


@pytest.mark.parametrize("numerator,divisor", [(True, 100), (1.0, 100), (1, 0), (1, 3)])
def test_bad_price_ratio(numerator, divisor):
    with pytest.raises(ValueError):
        gold.exact_price_decimal(numerator, divisor)


@pytest.mark.parametrize(
    "segment,size", [(1, 8), (3, 8), (6, 8), (12, 8), (9, 28), (9, 32), (1, 44), (1, 184)]
)
def test_supported_packet_layouts(segment, size):
    candidate = build(evidence(segment=segment, size=size))
    assert candidate.status == "candidate"
    assert candidate.provider_token == 256 + segment
    assert candidate.event_ts is None
    assert candidate.last_trade_time is None
    assert candidate.published_at is None
    assert candidate.effective_from is None
    assert candidate.effective_to is None
    assert candidate.canonical_contract_id is None
    assert candidate.decision_eligibility_asserted is False
    assert "EXCHANGE_EVENT_TIME_UNKNOWN" in candidate.quality_flags
    assert candidate.build_id == build(evidence(segment=segment, size=size)).build_id


def test_ltp_never_fabricates_ohlc_or_range():
    candidate = build(evidence())
    assert [feature.name for feature in candidate.features] == ["last_price"]
    assert candidate.features[0].decimal_value == "123.45"
    assert candidate.reference_source_fields_hash == "c" * 64


def test_range_is_exact_and_negative_inversion_preserved():
    candidate = build(evidence(size=44, prices={"high_raw": 11999, "low_raw": 12000}))
    values = {feature.name: feature for feature in candidate.features}
    assert values["intra_packet_range"].numerator == -1
    assert values["intra_packet_range"].decimal_value == "-0.01"
    assert "INVERTED_HIGH_LOW" in candidate.quality_flags


def test_observed_zero_stays_zero_not_null():
    candidate = build(evidence(prices={"last_price_raw": 0}))
    assert candidate.features[0].decimal_value == "0.00"
    assert candidate.features[0].numerator == 0
    assert "ZERO_LAST_PRICE" in candidate.quality_flags


@pytest.mark.parametrize("status", ["blocked", "ambiguous", "unresolved"])
def test_nonassociated_sources_have_no_features(status):
    source = evidence()
    source = replace(source, association=replace(source.association, status=status))
    candidate = build(source)
    assert candidate.status == "blocked"
    assert candidate.features == ()
    assert candidate.reason_code == "SOURCE_ASSOCIATION_NOT_UNIQUE"


def test_noncurrent_assessment_blocks():
    candidate = build(replace(evidence(), status="blocked"))
    assert candidate.status == "blocked"
    assert candidate.features == ()


@pytest.mark.parametrize(
    "changes",
    [
        {"price_divisor": 10_000},
        {"provider_segment": 2},
        {"mode": "full"},
        {"ordinal": 1},
        {"instrument_token": 0},
    ],
)
def test_packet_contract_changes_block(changes):
    source = evidence()
    association = source.association
    packet = replace(association.packet, **changes)
    source = replace(source, association=replace(association, packet=packet))
    assert build(source).status == "blocked"


@pytest.mark.parametrize(
    "raw",
    [
        (("last_price_raw", True),),
        (("last_price_raw", -1),),
        (("last_price_raw", 2**32),),
        (("last_price_raw", 1), ("last_price_raw", 2)),
        (("last_price_raw", 1), ("average_price_raw", 2)),
        (),
    ],
)
def test_raw_field_contract(raw):
    source = evidence()
    association = source.association
    source = replace(
        source, association=replace(association, packet=replace(association.packet, raw_fields=raw))
    )
    assert build(source).status == "blocked"
    assert build(source).features == ()


def test_packet_clock_is_not_replaced_by_trade_clock():
    source = evidence()
    association = source.association
    at = datetime(2026, 1, 1, tzinfo=UTC)
    packet = replace(association.packet, last_trade_time=at)
    candidate = build(replace(source, association=replace(association, packet=packet)))
    assert candidate.event_ts is None
    assert candidate.last_trade_time == at.isoformat()


def test_equivalent_timezones_have_same_build_identity():
    source = evidence()
    association = source.association
    at = datetime(2026, 1, 1, tzinfo=UTC)
    other = at.astimezone(timezone(timedelta(hours=5, minutes=30)))
    first = replace(
        source,
        association=replace(
            association, packet=replace(association.packet, exchange_event_time=at)
        ),
    )
    second = replace(
        source,
        association=replace(
            association, packet=replace(association.packet, exchange_event_time=other)
        ),
    )
    assert build(first) == build(second)


def test_naive_clock_blocks():
    source = evidence()
    association = source.association
    source = replace(
        source,
        association=replace(
            association,
            packet=replace(association.packet, exchange_event_time=datetime(2026, 1, 1)),
        ),
    )
    assert build(source).reason_code == "INVALID_PACKET_TIME"


def test_source_fingerprint_changes_build_identity():
    source = evidence()
    assert build(source).build_id != build(replace(source, evidence_fingerprint="c" * 64)).build_id


def test_public_entry_reverifies_and_forwards_pin(monkeypatch):
    connections = [object() for _ in range(4)]
    calls = []

    def read(*args, assessment_revision_id):
        assert list(args) == connections
        assert assessment_revision_id == PIN
        calls.append(1)
        return evidence()

    monkeypatch.setattr(gold, "read_packet_assessment", read)
    first = gold.build_quote_price_candidate(*connections, assessment_revision_id=PIN)
    second = gold.build_quote_price_candidate(*connections, assessment_revision_id=PIN)
    assert first == second
    assert calls == [1, 1]


def test_invalid_pin_before_reader(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Reader must not run")

    monkeypatch.setattr(gold, "read_packet_assessment", fail)
    with pytest.raises(ValueError):
        gold.build_quote_price_candidate(None, None, None, None, assessment_revision_id="BAD")


@pytest.mark.parametrize(
    "version_field,new_version",
    [
        ("READER_VERSION", "persisted-packet-association-consumer@2"),
        ("DECODER_VERSION", "kite-binary@2"),
    ],
)
def test_version_upgrade_requires_explicit_feature_review(monkeypatch, version_field, new_version):
    monkeypatch.setattr(gold, version_field, new_version)
    assert build(evidence()).reason_code == "UNSUPPORTED_SOURCE_VERSION"


def test_source_execution_error_is_not_a_candidate(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("source unavailable")

    monkeypatch.setattr(gold, "read_packet_assessment", fail)
    with pytest.raises(RuntimeError, match="source unavailable"):
        gold.build_quote_price_candidate(None, None, None, None, assessment_revision_id=PIN)


def test_changed_definition_fingerprint_changes_build_identity(monkeypatch):
    source = evidence()
    first = build(source)
    monkeypatch.setattr(gold, "DEFINITION_FINGERPRINT", "b" * 64)
    assert build(source).build_id != first.build_id


def test_invalidation_after_first_call_is_not_cached(monkeypatch):
    states = iter((evidence(), replace(evidence(), status="blocked", association=None)))
    monkeypatch.setattr(gold, "read_packet_assessment", lambda *a, **kw: next(states))
    assert (
        gold.build_quote_price_candidate(None, None, None, None, assessment_revision_id=PIN).status
        == "candidate"
    )
    assert (
        gold.build_quote_price_candidate(None, None, None, None, assessment_revision_id=PIN).status
        == "blocked"
    )
