"""Bounded underlying-identity assertions and evidence pins, not canonical identity."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

VERSION = "underlying-identity-assertion@1"
MAX_ARTIFACT_BYTES = 1048576
MAX_ASSERTION_BYTES = 16384
DEFINITION = (
    VERSION,
    "exact external namespace/id/asset-kind claims; case-sensitive, no alias inference",
    "ASSERTED/DISPUTED/WITHDRAWN are issuer assertions, never verified identity",
    "supporting evidence is an exact pinned Bronze payload byte interval",
    "byte integrity is not semantics, acquisition provenance or issuer authenticity",
    "no canonical IDs, provider label mapping, temporal validity or decision authority",
)


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


DEFINITION_FINGERPRINT = digest(DEFINITION)


def pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def strict_json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_ASSERTION_JSON_KEY")
            result[key] = value
        return result

    def invalid(_text: str) -> Any:
        raise ValueError("NONFINITE_ASSERTION_JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


@dataclass(frozen=True)
class UnderlyingAssertionRequest:
    namespace: str
    external_id: str
    asset_kind: str
    asserted_issuer: str
    assertion: str
    bronze_capture_event_id: str
    bronze_envelope_hash: str
    evidence_payload_hash: str
    evidence_byte_start: int
    evidence_byte_end: int
    evidence_fragment_sha256: str
    rationale_code: str

    def __post_init__(self) -> None:
        for value, limit in (
            (self.namespace, 64),
            (self.external_id, 256),
            (self.asserted_issuer, 128),
        ):
            if not isinstance(value, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._:/-]{0," + str(limit - 1) + "}", value
            ):
                raise ValueError("EXPLICIT_BOUNDED_IDENTITY_ASSERTION_IDENTIFIERS_REQUIRED")
        if self.asset_kind not in {"INDEX", "EQUITY"} or self.assertion not in {
            "ASSERTED",
            "DISPUTED",
            "WITHDRAWN",
        }:
            raise ValueError("UNSUPPORTED_UNDERLYING_ASSERTION_KIND")
        if not isinstance(self.rationale_code, str) or not re.fullmatch(
            r"[A-Z0-9_]{1,64}", self.rationale_code
        ):
            raise ValueError("BOUNDED_ASSERTION_REASON_CODE_REQUIRED")
        if not all(
            pin(x)
            for x in (
                self.bronze_capture_event_id,
                self.bronze_envelope_hash,
                self.evidence_payload_hash,
                self.evidence_fragment_sha256,
            )
        ):
            raise ValueError("EXACT_ASSERTION_EVIDENCE_PINS_REQUIRED")
        if (
            type(self.evidence_byte_start) is not int
            or type(self.evidence_byte_end) is not int
            or not 0 <= self.evidence_byte_start < self.evidence_byte_end <= MAX_ARTIFACT_BYTES
        ):
            raise ValueError("BOUNDED_NONEMPTY_ASSERTION_EVIDENCE_INTERVAL_REQUIRED")


@dataclass(frozen=True)
class UnderlyingAssertion:
    assertion_id: str
    version: str
    definition_fingerprint: str
    subject_scope_id: str
    request_json: str
    canonical_underlying_id: None = None
    identity_verified: bool = False
    issuer_authenticated: bool = False
    historical_validity_asserted: bool = False
    availability_evidence_verified: bool = False
    decision_eligibility_asserted: bool = False


def make_underlying_assertion(request: UnderlyingAssertionRequest) -> UnderlyingAssertion:
    if not isinstance(request, UnderlyingAssertionRequest):
        raise TypeError("TYPED_UNDERLYING_ASSERTION_REQUEST_REQUIRED")
    checked = UnderlyingAssertionRequest(**asdict(request))
    scope = digest([VERSION, checked.namespace, checked.external_id, checked.asset_kind])
    value = UnderlyingAssertion(
        "", VERSION, DEFINITION_FINGERPRINT, scope, canonical(asdict(checked))
    )
    content = asdict(value)
    del content["assertion_id"]
    return UnderlyingAssertion(**dict(content, assertion_id=digest(content)))


def encode_underlying_assertion(value: UnderlyingAssertion) -> bytes:
    if (
        not isinstance(value.request_json, str)
        or len(value.request_json.encode()) > MAX_ASSERTION_BYTES
    ):
        raise ValueError("UNDERLYING_ASSERTION_REQUEST_BYTE_LIMIT")
    request = strict_json(value.request_json)
    if not isinstance(request, dict):
        raise ValueError("ASSERTION_REQUEST_SCHEMA_MISMATCH")
    expected = make_underlying_assertion(UnderlyingAssertionRequest(**request))
    if canonical(asdict(value)) != canonical(asdict(expected)):
        raise ValueError("UNDERLYING_ASSERTION_CONTENT_MISMATCH")
    raw = canonical(asdict(value)).encode()
    if len(raw) > MAX_ASSERTION_BYTES:
        raise ValueError("UNDERLYING_ASSERTION_BYTE_LIMIT")
    return raw


def decode_underlying_assertion(raw: bytes, *, expected_assertion_id: str) -> UnderlyingAssertion:
    if not isinstance(raw, bytes) or len(raw) > MAX_ASSERTION_BYTES:
        raise ValueError("UNDERLYING_ASSERTION_BYTE_LIMIT")
    value = strict_json(raw.decode("utf-8"))
    if not isinstance(value, dict) or set(value) != set(UnderlyingAssertion.__dataclass_fields__):
        raise ValueError("UNDERLYING_ASSERTION_SCHEMA_MISMATCH")
    result = UnderlyingAssertion(**value)
    if not pin(expected_assertion_id) or result.assertion_id != expected_assertion_id:
        raise ValueError("UNDERLYING_ASSERTION_PIN_MISMATCH")
    if encode_underlying_assertion(result) != raw:
        raise ValueError("UNDERLYING_ASSERTION_NONCANONICAL_OR_CHANGED")
    return result


def check_supporting_bytes(request: UnderlyingAssertionRequest, payload: bytes) -> None:
    """Only byte/range consistency, never interpretation or authenticity."""
    UnderlyingAssertionRequest(**asdict(request))
    if not isinstance(payload, bytes) or len(payload) > MAX_ARTIFACT_BYTES:
        raise ValueError("UNDERLYING_SUPPORT_BYTE_LIMIT")
    if hashlib.sha256(payload).hexdigest() != request.evidence_payload_hash:
        raise ValueError("UNDERLYING_SUPPORT_PAYLOAD_HASH_MISMATCH")
    if request.evidence_byte_end > len(payload):
        raise ValueError("UNDERLYING_SUPPORT_INTERVAL_OUTSIDE_PAYLOAD")
    fragment = payload[request.evidence_byte_start : request.evidence_byte_end]
    if hashlib.sha256(fragment).hexdigest() != request.evidence_fragment_sha256:
        raise ValueError("UNDERLYING_SUPPORT_FRAGMENT_HASH_MISMATCH")
