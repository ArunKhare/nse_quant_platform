"""Platform-owned detached proof artifacts; no issuer/key authority inference."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

VERSION = "statement-signature-artifact@1"
PAYLOAD_FORMAT = "statement_signature_json@1"
MAX_BYTES = 4096
FIELDS = frozenset(
    {
        "schema",
        "assertion_id",
        "record_id",
        "payload_sha256",
        "public_key_base64",
        "signature_base64",
    }
)


class SignatureArtifactRejected(ValueError):
    """Fixed-code rejection, never arbitrary artifact contents in diagnostics."""


@dataclass(frozen=True)
class SignatureArtifact:
    version: str
    artifact_sha256: str
    assertion_id: str
    record_id: str
    payload_sha256: str
    public_key: bytes
    signature: bytes


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise SignatureArtifactRejected("SIGNATURE_ARTIFACT_DUPLICATE_KEY")
        value[key] = item
    return value


def _invalid(_value: str) -> Any:
    raise SignatureArtifactRejected("SIGNATURE_ARTIFACT_NONFINITE_JSON")


def _binary(value: object, length: int) -> bytes:
    if not isinstance(value, str):
        raise SignatureArtifactRejected("SIGNATURE_ARTIFACT_BINARY_ENCODING_INVALID")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise SignatureArtifactRejected("SIGNATURE_ARTIFACT_BINARY_ENCODING_INVALID") from None
    if len(raw) != length or base64.b64encode(raw).decode("ascii") != value:
        raise SignatureArtifactRejected("SIGNATURE_ARTIFACT_BINARY_ENCODING_INVALID")
    return raw


def parse_signature_artifact(raw: bytes) -> SignatureArtifact:
    """Exactly one canonical UTF8 JSON object, no newline, alternate encoding or salvage."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise SignatureArtifactRejected("SIGNATURE_ARTIFACT_BYTES_LIMIT")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_invalid)
        if not isinstance(value, dict) or set(value) != FIELDS or value["schema"] != VERSION:
            raise SignatureArtifactRejected("SIGNATURE_ARTIFACT_SCHEMA_INVALID")
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if canonical.encode("utf-8") != raw:
            raise SignatureArtifactRejected("SIGNATURE_ARTIFACT_NONCANONICAL")
        if any(
            not isinstance(value[key], str) or re.fullmatch(r"[a-f0-9]{64}", value[key]) is None
            for key in ("assertion_id", "payload_sha256")
        ) or (
            not isinstance(value["record_id"], str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}", value["record_id"]) is None
        ):
            raise SignatureArtifactRejected("SIGNATURE_ARTIFACT_TARGET_INVALID")
        key = _binary(value["public_key_base64"], 32)
        signature = _binary(value["signature_base64"], 64)
    except SignatureArtifactRejected:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise SignatureArtifactRejected("SIGNATURE_ARTIFACT_MALFORMED") from None
    return SignatureArtifact(
        VERSION,
        hashlib.sha256(raw).hexdigest(),
        value["assertion_id"],
        value["record_id"],
        value["payload_sha256"],
        key,
        signature,
    )
