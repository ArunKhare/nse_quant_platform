"""Signed causal key transitions under a supplied root, never authenticated authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERSION = "observed-governance-key-lifecycle@1"
EVENT_VERSION = "observed-governance-key-event@1"
DOMAIN = b"nse-quant/observed-governance-key-event/ed25519/v1\x00"
MAX_DOCUMENT_BYTES = 4096
MAX_RECORD_BYTES = 12288
MAX_EVENTS = 64
MAX_CHAIN_BYTES = 524288


class KeyLifecycleRejected(ValueError):
    """Fixed diagnostic code; no raw document or exception text."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _identifier(value: object) -> bool:
    return (
        type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}", value) is not None
    )


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise KeyLifecycleRejected("KEY_LIFECYCLE_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _invalid(_value: str) -> Any:
    raise KeyLifecycleRejected("KEY_LIFECYCLE_NONFINITE_JSON")


def document(raw: bytes, maximum: int) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise KeyLifecycleRejected("KEY_LIFECYCLE_BYTE_BOUND")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_invalid)
        if not isinstance(value, dict) or canonical(value) != raw:
            raise KeyLifecycleRejected("KEY_LIFECYCLE_CANONICAL_OBJECT_REQUIRED")
        return value
    except KeyLifecycleRejected:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise KeyLifecycleRejected("KEY_LIFECYCLE_MALFORMED_JSON") from None


def unhex(value: object, size: int) -> bytes:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{" + str(size * 2) + "}", value) is None:
        raise KeyLifecycleRejected("KEY_LIFECYCLE_EXACT_HEX_REQUIRED")
    return bytes.fromhex(value)


@dataclass(frozen=True)
class LifecycleScope:
    series_id: str
    namespace: str
    asset_kind: str
    policy_id: str

    def __post_init__(self) -> None:
        if not all(
            _identifier(x) for x in (self.series_id, self.namespace, self.policy_id)
        ) or self.asset_kind not in ("INDEX", "EQUITY"):
            raise KeyLifecycleRejected("KEY_LIFECYCLE_EXACT_SCOPE_REQUIRED")


def signing_message(raw_document: bytes, role: str) -> bytes:
    if type(raw_document) is not bytes or not 0 < len(raw_document) <= MAX_DOCUMENT_BYTES:
        raise KeyLifecycleRejected("KEY_LIFECYCLE_DOCUMENT_BOUND")
    if role not in ("CURRENT", "SUCCESSOR"):
        raise KeyLifecycleRejected("KEY_LIFECYCLE_SIGNATURE_ROLE")
    label = role.encode()
    return (
        DOMAIN
        + len(label).to_bytes(2, "big")
        + label
        + len(raw_document).to_bytes(8, "big")
        + raw_document
    )


def encode_signed_event(
    raw_document: bytes,
    signature: bytes,
    successor_signature: bytes | None,
) -> bytes:
    document(raw_document, MAX_DOCUMENT_BYTES)
    if (
        type(signature) is not bytes
        or len(signature) != 64
        or (
            successor_signature is not None
            and (type(successor_signature) is not bytes or len(successor_signature) != 64)
        )
    ):
        raise KeyLifecycleRejected("KEY_LIFECYCLE_SIGNATURE_SHAPE")
    raw = canonical(
        dict(
            document_hex=raw_document.hex(),
            signature_hex=signature.hex(),
            successor_signature_hex=(
                None if successor_signature is None else successor_signature.hex()
            ),
        )
    )
    if len(raw) > MAX_RECORD_BYTES:
        raise KeyLifecycleRejected("KEY_LIFECYCLE_RECORD_BOUND")
    return raw


@dataclass(frozen=True)
class ObservedKeyLifecycle:
    version: str
    scope: LifecycleScope
    root_key_sha256: str
    record_sha256s: tuple[str, ...]
    active_public_key_hex: str | None
    retired_key_sha256s: tuple[str, ...]
    evidence_fingerprint: str
    signed_causal_constraints_satisfied: bool = True
    root_authority_authenticated: bool = False
    namespace_authority_verified: bool = False
    global_history_completeness_verified: bool = False
    key_currentness_verified: bool = False
    authorized_revocation_asserted: bool = False
    identity_verified: bool = False
    availability_evidence_verified: bool = False
    decision_eligibility_asserted: bool = False


def inspect_key_lifecycle(
    records: tuple[bytes, ...],
    *,
    expected_record_sha256s: tuple[str, ...],
    root_public_key: bytes,
    expected_root_key_sha256: str,
    scope: LifecycleScope,
) -> ObservedKeyLifecycle:
    """Every supplied record verifies. No sorting, prefix salvage, discovery or latest selection.

    ROTATE requires the active key's signature AND the successor's possession proof.
    Rotation retires the old key permanently within this supplied chain. REVOKE is
    terminal and only the active key can sign it. No emergency recovery is implied.
    Caller-pinned roots can be attacker chosen: signatures never authenticate authority.
    """
    if (
        type(scope) is not LifecycleScope
        or type(records) is not tuple
        or not 1 <= len(records) <= MAX_EVENTS
        or type(expected_record_sha256s) is not tuple
        or len(expected_record_sha256s) != len(records)
        or any(not pin(x) for x in expected_record_sha256s)
        or type(root_public_key) is not bytes
        or len(root_public_key) != 32
        or not pin(expected_root_key_sha256)
    ):
        raise KeyLifecycleRejected("KEY_LIFECYCLE_EXACT_INPUTS_REQUIRED")
    scope = LifecycleScope(**asdict(scope))
    if sha(root_public_key) != expected_root_key_sha256:
        raise KeyLifecycleRejected("KEY_LIFECYCLE_ROOT_PIN_MISMATCH")
    total = 0
    for raw in records:
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_RECORD_BYTES:
            raise KeyLifecycleRejected("KEY_LIFECYCLE_RECORD_BOUND")
        total += len(raw)
    if total > MAX_CHAIN_BYTES:
        raise KeyLifecycleRejected("KEY_LIFECYCLE_AGGREGATE_BOUND")
    active: bytes | None = root_public_key
    retired: set[str] = set()
    introduced = {expected_root_key_sha256}
    previous: str | None = None
    pairs = zip(records, expected_record_sha256s, strict=True)
    for sequence, (raw, expected) in enumerate(pairs, 1):
        if sha(raw) != expected:
            raise KeyLifecycleRejected("KEY_LIFECYCLE_RECORD_PIN_MISMATCH")
        envelope = document(raw, MAX_RECORD_BYTES)
        if set(envelope) != {"document_hex", "signature_hex", "successor_signature_hex"}:
            raise KeyLifecycleRejected("KEY_LIFECYCLE_ENVELOPE_SCHEMA")
        text = envelope["document_hex"]
        if type(text) is not str or not 0 < len(text) <= MAX_DOCUMENT_BYTES * 2 or len(text) % 2:
            raise KeyLifecycleRejected("KEY_LIFECYCLE_DOCUMENT_BOUND")
        if re.fullmatch(r"[a-f0-9]+", text) is None:
            raise KeyLifecycleRejected("KEY_LIFECYCLE_EXACT_HEX_REQUIRED")
        body = bytes.fromhex(text)
        event = document(body, MAX_DOCUMENT_BYTES)
        if set(event) != {
            "schema",
            "scope",
            "root_key_sha256",
            "sequence",
            "predecessor_sha256",
            "action",
            "subject_key_sha256",
            "successor_public_key_hex",
        }:
            raise KeyLifecycleRejected("KEY_LIFECYCLE_EVENT_SCHEMA")
        if (
            event["schema"] != EVENT_VERSION
            or event["scope"] != asdict(scope)
            or event["root_key_sha256"] != expected_root_key_sha256
            or type(event["sequence"]) is not int
            or event["sequence"] != sequence
            or event["predecessor_sha256"] != previous
        ):
            raise KeyLifecycleRejected("KEY_LIFECYCLE_SCOPE_OR_CAUSAL_CHAIN_MISMATCH")
        if active is None:
            raise KeyLifecycleRejected("KEY_LIFECYCLE_TERMINAL_REVOCATION")
        if event["subject_key_sha256"] != sha(active):
            raise KeyLifecycleRejected("KEY_LIFECYCLE_ACTIVE_SUBJECT_REQUIRED")
        signature = unhex(envelope["signature_hex"], 64)
        try:
            Ed25519PublicKey.from_public_bytes(active).verify(
                signature,
                signing_message(body, "CURRENT"),
            )
        except InvalidSignature:
            raise KeyLifecycleRejected("KEY_LIFECYCLE_CURRENT_SIGNATURE_INVALID") from None
        if event["action"] == "ROTATE":
            successor = unhex(event["successor_public_key_hex"], 32)
            if sha(successor) in introduced:
                raise KeyLifecycleRejected("KEY_LIFECYCLE_REACTIVATION_OR_SELF_ROTATION")
            proof = unhex(envelope["successor_signature_hex"], 64)
            try:
                Ed25519PublicKey.from_public_bytes(successor).verify(
                    proof,
                    signing_message(body, "SUCCESSOR"),
                )
            except InvalidSignature:
                raise KeyLifecycleRejected("KEY_LIFECYCLE_SUCCESSOR_SIGNATURE_INVALID") from None
            retired.add(sha(active))
            introduced.add(sha(successor))
            active = successor
        elif event["action"] == "REVOKE":
            if (
                event["successor_public_key_hex"] is not None
                or envelope["successor_signature_hex"] is not None
            ):
                raise KeyLifecycleRejected("KEY_LIFECYCLE_REVOCATION_SHAPE")
            retired.add(sha(active))
            active = None
        else:
            raise KeyLifecycleRejected("KEY_LIFECYCLE_ACTION_UNSUPPORTED")
        previous = expected
    active_hex = None if active is None else active.hex()
    unsigned = dict(
        version=VERSION,
        scope=asdict(scope),
        root_key_sha256=expected_root_key_sha256,
        record_sha256s=expected_record_sha256s,
        active_public_key_hex=active_hex,
        retired_key_sha256s=tuple(sorted(retired)),
    )
    return ObservedKeyLifecycle(
        VERSION,
        scope,
        expected_root_key_sha256,
        expected_record_sha256s,
        active_hex,
        tuple(sorted(retired)),
        sha(canonical(unsigned)),
    )
