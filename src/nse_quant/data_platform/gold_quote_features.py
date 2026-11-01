"""Versioned exact price candidates; no persistence, publication or eligibility."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.kite_decoder import DECODER_VERSION
from nse_quant.data_platform.packet_association_reader import (
    READER_VERSION,
    PersistedAssociationEvidence,
    read_packet_assessment,
)

FEATURE_VERSION = "provider-packet-price-fields@1"
SUPPORTED_READER = "persisted-packet-association-consumer@1"
DEFINITION = (
    FEATURE_VERSION,
    "input: persisted-packet-association-consumer@1 / associated / kite-binary@1",
    "fields: last_price,average_price,open,high,low,close",
    "value: exact signed numerator/provider_price_divisor; fixed-scale decimal",
    "intra_packet_range: high_raw-low_raw; absent unless both fields present",
    "zero remains observed zero; inverted range remains negative and flagged",
    "event_ts: exchange_event_time only; receipt is never a substitute",
    "no currency, contract identity, publication, validity or eligibility assertion",
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


DEFINITION_FINGERPRINT = _hash(DEFINITION)


def _pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _instant(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("AWARE_PACKET_TIME_REQUIRED")
    return value.astimezone(UTC).isoformat()


def exact_price_decimal(numerator: int, denominator: int) -> str:
    """Exact fixed-scale rendering, independent of float/Decimal contexts."""
    if type(numerator) is not int or type(denominator) is not int:
        raise ValueError("INTEGER_PRICE_RATIO_REQUIRED")
    if denominator not in {100, 10_000, 10_000_000}:
        raise ValueError("SUPPORTED_PROVIDER_DIVISOR_REQUIRED")
    whole, fractional = divmod(abs(numerator), denominator)
    digits = len(str(denominator)) - 1
    sign = "-" if numerator < 0 else ""
    return f"{sign}{whole}.{fractional:0{digits}d}"


@dataclass(frozen=True)
class ExactPriceFeature:
    name: str
    numerator: int
    denominator: int
    decimal_value: str


@dataclass(frozen=True)
class GoldQuoteCandidate:
    build_id: str
    feature_version: str
    definition_fingerprint: str
    source_assessment_revision_id: str
    status: str
    reason_code: str
    source_evidence_fingerprint: str | None = None
    source_association_fingerprint: str | None = None
    source_frame_revision_id: str | None = None
    source_packet_ordinal: int | None = None
    reference_assessment_revision_id: str | None = None
    reference_row_ordinal: int | None = None
    reference_source_fields_hash: str | None = None
    provider_token: int | None = None
    price_divisor: int | None = None
    event_ts: str | None = None
    last_trade_time: str | None = None
    features: tuple[ExactPriceFeature, ...] = ()
    quality_flags: tuple[str, ...] = ()
    canonical_contract_id: None = None
    published_at: None = None
    effective_from: None = None
    effective_to: None = None
    decision_eligibility_asserted: bool = False


def _derive_price_candidate(
    evidence: PersistedAssociationEvidence,
    assessment_revision_id: str,
) -> GoldQuoteCandidate:
    """Internal pure kernel. Supplied dataclasses are not source attestations."""

    def finish(candidate: GoldQuoteCandidate) -> GoldQuoteCandidate:
        return replace(candidate, build_id=_hash(asdict(candidate)))

    def blocked(reason: str) -> GoldQuoteCandidate:
        return finish(
            GoldQuoteCandidate(
                "",
                FEATURE_VERSION,
                DEFINITION_FINGERPRINT,
                assessment_revision_id,
                "blocked",
                reason,
            )
        )

    if (
        READER_VERSION != SUPPORTED_READER
        or evidence.reader_version != SUPPORTED_READER
        or DECODER_VERSION != "kite-binary@1"
    ):
        return blocked("UNSUPPORTED_SOURCE_VERSION")
    if evidence.assessment_revision_id != assessment_revision_id:
        return blocked("SOURCE_READER_CONTRACT_MISMATCH")
    if evidence.status != "verified_current":
        return blocked("SOURCE_ASSESSMENT_NOT_CURRENT")
    association = evidence.association
    if association is None or association.status != "associated":
        return blocked("SOURCE_ASSOCIATION_NOT_UNIQUE")
    if (
        not _pin(evidence.evidence_fingerprint)
        or evidence.active_revision_ids != (assessment_revision_id,)
        or not evidence.successful_attempt_job_ids
        or evidence.publication_asserted is not False
        or evidence.historical_validity_asserted is not False
        or evidence.decision_eligibility_asserted is not False
        or association.association_version != "pinned-packet-reference@1"
        or association.evidence_mode != "PINNED_CURRENT_ROW_ASSOCIATION_ONLY"
        or association.canonical_contract_id is not None
        or association.publication_asserted is not False
        or association.historical_validity_asserted is not False
        or association.decision_eligibility_asserted is not False
        or not _pin(association.association_fingerprint)
        or not _pin(association.frame_revision_id)
        or not _pin(association.reference_assessment_revision_id)
    ):
        return blocked("SOURCE_EVIDENCE_CONTRACT_MISMATCH")
    packet, lookup = association.packet, association.reference_lookup
    if packet is None or lookup is None or lookup.status != "matched":
        return blocked("SOURCE_ROW_EVIDENCE_MISSING")
    if (
        lookup.resolver_version != "native-reference-consumer@1"
        or lookup.evidence_mode != "PINNED_CURRENT_EVIDENCE_ONLY"
        or lookup.reason_code != "UNIQUE_TOKEN_ROW"
        or lookup.active_revision_ids != (association.reference_assessment_revision_id,)
        or lookup.assessment_revision_id != association.reference_assessment_revision_id
        or lookup.instrument_token != packet.instrument_token
        or len(lookup.candidates) != 1
        or lookup.canonical_contract_id is not None
        or lookup.publication_asserted is not False
        or lookup.historical_validity_asserted is not False
    ):
        return blocked("SOURCE_ROW_EVIDENCE_MISMATCH")
    row = lookup.candidates[0]
    if (
        row.assessment_revision_id != association.reference_assessment_revision_id
        or type(row.row_ordinal) is not int
        or not 0 <= row.row_ordinal < 200_000
        or not _pin(row.source_fields_hash)
    ):
        return blocked("INVALID_REFERENCE_ROW_PIN")
    if type(packet.instrument_token) is not int or not 0 < packet.instrument_token < 2**32:
        return blocked("INVALID_PROVIDER_TOKEN")
    segment = packet.instrument_token & 255
    divisor = 10_000_000 if segment == 3 else 10_000 if segment in {6, 12} else 100
    expected_mode = "ltp" if packet.size == 8 else "quote" if packet.size in {28, 44} else "full"
    if (
        type(packet.instrument_token) is not int
        or not 0 < packet.instrument_token < 2**32
        or segment not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 12}
        or type(packet.provider_segment) is not int
        or packet.provider_segment != segment
        or type(packet.price_divisor) is not int
        or packet.price_divisor != divisor
        or packet.size not in {8, 28, 32, 44, 184}
        or packet.mode != expected_mode
        or (packet.size in {28, 32} and segment != 9)
        or (packet.size in {44, 184} and segment == 9)
        or type(packet.ordinal) is not int
        or packet.ordinal != association.packet_ordinal
        or type(association.packet_ordinal) is not int
        or not 0 <= packet.ordinal < 4096
    ):
        return blocked("PACKET_LAYOUT_CONTRACT_MISMATCH")
    expected_fields = {"last_price_raw"}
    if packet.size in {28, 32}:
        expected_fields |= {"open_raw", "high_raw", "low_raw", "close_raw", "index_change_bits"}
    if packet.size == 32:
        expected_fields.add("exchange_epoch_seconds")
    if packet.size in {44, 184}:
        expected_fields |= {
            "last_quantity",
            "average_price_raw",
            "volume",
            "buy_quantity",
            "sell_quantity",
            "open_raw",
            "high_raw",
            "low_raw",
            "close_raw",
        }
    if packet.size == 184:
        expected_fields |= {
            "last_trade_epoch_seconds",
            "oi",
            "oi_high",
            "oi_low",
            "exchange_epoch_seconds",
        }
    raw = dict(packet.raw_fields)
    if (
        len(raw) != len(packet.raw_fields)
        or set(raw) != expected_fields
        or len(raw) > 32
        or any(type(number) is not int or not 0 <= number < 2**32 for number in raw.values())
    ):
        return blocked("RAW_FIELD_CONTRACT_MISMATCH")
    if packet.size != 8 and not {"open_raw", "high_raw", "low_raw", "close_raw"} <= raw.keys():
        return blocked("RAW_PRICE_FIELDS_MISSING")
    features: list[ExactPriceFeature] = []
    quality: list[str] = []
    for field in ("last_price", "average_price", "open", "high", "low", "close"):
        key = field + "_raw"
        if key in raw:
            number = raw[key]
            features.append(
                ExactPriceFeature(
                    field,
                    number,
                    divisor,
                    exact_price_decimal(number, divisor),
                )
            )
            if number == 0:
                quality.append("ZERO_" + field.upper())
    if "high_raw" in raw and "low_raw" in raw:
        span = raw["high_raw"] - raw["low_raw"]
        features.append(
            ExactPriceFeature(
                "intra_packet_range",
                span,
                divisor,
                exact_price_decimal(span, divisor),
            )
        )
        if span < 0:
            quality.append("INVERTED_HIGH_LOW")
    try:
        event_time = _instant(packet.exchange_event_time)
        trade_time = _instant(packet.last_trade_time)
    except (ValueError, TypeError, AttributeError):
        return blocked("INVALID_PACKET_TIME")
    if event_time is None:
        quality.append("EXCHANGE_EVENT_TIME_UNKNOWN")
    candidate = GoldQuoteCandidate(
        "",
        FEATURE_VERSION,
        DEFINITION_FINGERPRINT,
        assessment_revision_id,
        "candidate",
        "EXACT_PROVIDER_PRICE_FIELDS",
        evidence.evidence_fingerprint,
        association.association_fingerprint,
        association.frame_revision_id,
        packet.ordinal,
        association.reference_assessment_revision_id,
        row.row_ordinal,
        row.source_fields_hash,
        packet.instrument_token,
        divisor,
        event_time,
        trade_time,
        tuple(features),
        tuple(quality),
    )
    return finish(candidate)


def build_quote_price_candidate(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    *,
    assessment_revision_id: str,
) -> GoldQuoteCandidate:
    """Always reverify through the persisted consumer; reads only, no data migration.

    This is an in-memory Gold candidate, NOT a persisted Gold build, audited write,
    publication, historical validity claim or decision-ready feature bundle.
    """
    if not _pin(assessment_revision_id):
        raise ValueError("EXACT_ASSESSMENT_REVISION_REQUIRED")
    evidence = read_packet_assessment(
        bronze,
        frame_silver,
        reference_silver,
        assessments,
        assessment_revision_id=assessment_revision_id,
    )
    return _derive_price_candidate(evidence, assessment_revision_id)
