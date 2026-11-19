"""Explicit pinned packet-to-row evidence, never timeless token/contract identity."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.kite_decoder import Packet
from nse_quant.data_platform.kite_frame_reader import READER_VERSION, read_kite_frame
from nse_quant.data_platform.native_reference_reader import (
    NativeReferenceLookup,
    lookup_native_reference,
)
from nse_quant.data_platform.reference_supersession import RESOLVER_VERSION

ASSOCIATION_VERSION = "pinned-packet-reference@1"
MAX_PACKETS = 4096
MAX_CANDIDATES = 1000


def _hash_pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _fingerprint(value: object) -> str:
    def timestamp(item: object) -> str:
        if not isinstance(item, datetime) or item.tzinfo is None or item.utcoffset() is None:
            raise ValueError("AWARE_PACKET_TIME_REQUIRED")
        return item.astimezone(UTC).isoformat()

    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=timestamp
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class PacketReferenceAssociation:
    association_version: str
    frame_revision_id: str
    packet_ordinal: int
    reference_assessment_revision_id: str
    status: str
    reason_code: str
    frame_evidence_fingerprint: str | None = None
    packet: Packet | None = None
    reference_lookup: NativeReferenceLookup | None = None
    association_fingerprint: str | None = None
    evidence_mode: str = "PINNED_CURRENT_ROW_ASSOCIATION_ONLY"
    canonical_contract_id: None = None
    publication_asserted: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False


def associate_packet_reference(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    *,
    frame_revision_id: str,
    packet_ordinal: int,
    reference_assessment_revision_id: str,
) -> PacketReferenceAssociation:
    """Caller owns read-only connections, without enclosing transactions.

    Reference Silver may equal frame Silver. Reads are sequential, not an atomic
    cross-database snapshot. No caching or current/latest reference selection.
    Exceptions from readers propagate; evidence rejection is not execution failure.
    Association does not apply temporal claims or persist/publicize anything.
    """
    if not _hash_pin(frame_revision_id) or not _hash_pin(reference_assessment_revision_id):
        raise ValueError("EXACT_FRAME_AND_REFERENCE_PINS_REQUIRED")
    if type(packet_ordinal) is not int or not 0 <= packet_ordinal < MAX_PACKETS:
        raise ValueError("INVALID_PACKET_ORDINAL")

    def outcome(
        reason: str,
        status: str = "blocked",
        frame_fingerprint: str | None = None,
        packet: Packet | None = None,
        lookup: NativeReferenceLookup | None = None,
    ) -> PacketReferenceAssociation:
        result = PacketReferenceAssociation(
            ASSOCIATION_VERSION,
            frame_revision_id,
            packet_ordinal,
            reference_assessment_revision_id,
            status,
            reason,
            frame_fingerprint,
            packet,
            lookup,
        )
        # Fingerprint includes blocked outcomes too; never a durable publication.
        fingerprint = _fingerprint(asdict(result))
        return PacketReferenceAssociation(
            ASSOCIATION_VERSION,
            frame_revision_id,
            packet_ordinal,
            reference_assessment_revision_id,
            status,
            reason,
            frame_fingerprint,
            packet,
            lookup,
            fingerprint,
        )

    frame = read_kite_frame(bronze, frame_silver, revision_id=frame_revision_id)
    if frame.reader_version != READER_VERSION or frame.revision_id != frame_revision_id:
        return outcome("FRAME_READER_CONTRACT_MISMATCH")
    if frame.status != "verified":
        return outcome("FRAME_" + frame.reason_code)
    if (
        not _hash_pin(frame.evidence_fingerprint)
        or frame.publication_asserted
        or frame.historical_validity_asserted
        or frame.decision_eligibility_asserted
        or frame.decoded is None
    ):
        return outcome("FRAME_READER_CONTRACT_MISMATCH")
    fingerprint = frame.evidence_fingerprint
    decoded = frame.decoded
    if decoded.classification != "quote_ticks" or decoded.reason_code != "DECODED":
        return outcome("FRAME_NOT_QUOTE_TICKS", frame_fingerprint=fingerprint)
    if not 0 < len(decoded.packets) <= MAX_PACKETS:
        return outcome("FRAME_PACKET_CONTRACT_MISMATCH", frame_fingerprint=fingerprint)
    if packet_ordinal >= len(decoded.packets):
        return outcome("PACKET_NOT_IN_PINNED_FRAME", frame_fingerprint=fingerprint)
    packet = decoded.packets[packet_ordinal]
    if type(packet.ordinal) is not int or packet.ordinal != packet_ordinal:
        return outcome("PACKET_ORDINAL_MISMATCH", frame_fingerprint=fingerprint)
    if type(packet.instrument_token) is not int or not 0 < packet.instrument_token < 2**32:
        return outcome("INVALID_PACKET_PROVIDER_TOKEN", frame_fingerprint=fingerprint)
    lookup = lookup_native_reference(
        bronze,
        reference_silver,
        assessment_revision_id=reference_assessment_revision_id,
        instrument_token=packet.instrument_token,
    )
    if (
        lookup.resolver_version != RESOLVER_VERSION
        or lookup.assessment_revision_id != reference_assessment_revision_id
        or type(lookup.instrument_token) is not int
        or lookup.instrument_token != packet.instrument_token
        or lookup.evidence_mode != "PINNED_CURRENT_EVIDENCE_ONLY"
        or lookup.canonical_contract_id is not None
        or lookup.publication_asserted
        or lookup.historical_validity_asserted
        or lookup.status not in {"matched", "ambiguous", "unresolved", "blocked"}
    ):
        return outcome(
            "REFERENCE_READER_CONTRACT_MISMATCH", frame_fingerprint=fingerprint, packet=packet
        )
    candidates = lookup.candidates
    if (
        len(candidates) > MAX_CANDIDATES
        or any(
            row.assessment_revision_id != reference_assessment_revision_id
            or type(row.row_ordinal) is not int
            or not 0 <= row.row_ordinal < 200_000
            or not _hash_pin(row.source_fields_hash)
            for row in candidates
        )
        or len({row.row_ordinal for row in candidates}) != len(candidates)
    ):
        return outcome(
            "REFERENCE_CANDIDATE_CONTRACT_MISMATCH", frame_fingerprint=fingerprint, packet=packet
        )
    if lookup.status in {"matched", "ambiguous", "unresolved"}:
        if lookup.active_revision_ids != (reference_assessment_revision_id,):
            return outcome(
                "REFERENCE_ACTIVE_PIN_MISMATCH", frame_fingerprint=fingerprint, packet=packet
            )
        expected = {
            "matched": "UNIQUE_TOKEN_ROW",
            "ambiguous": "MULTIPLE_TOKEN_ROWS",
            "unresolved": "TOKEN_NOT_IN_PINNED_ASSESSMENT",
        }
        if (
            lookup.reason_code != expected[lookup.status]
            or (lookup.status == "matched" and len(candidates) != 1)
            or (lookup.status == "ambiguous" and len(candidates) < 2)
            or (lookup.status == "unresolved" and bool(candidates))
        ):
            return outcome(
                "REFERENCE_STATUS_CONTRACT_MISMATCH", frame_fingerprint=fingerprint, packet=packet
            )
    if lookup.status == "matched":
        return outcome("UNIQUE_PINNED_REFERENCE_ROW", "associated", fingerprint, packet, lookup)
    return outcome("REFERENCE_" + lookup.reason_code, lookup.status, fingerprint, packet, lookup)
