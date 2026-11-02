"""Deterministic DTO observation digests and explicit reviewed checkpoint pins."""

from __future__ import annotations

import hashlib
import json
import re


def hash_pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def check_reviewed_pins(
    *,
    actual_checkpoint_id: str,
    actual_history_fingerprint: str,
    expected_checkpoint_id: str,
    expected_history_fingerprint: str,
) -> bool:
    if not all(
        hash_pin(value)
        for value in (
            actual_checkpoint_id,
            actual_history_fingerprint,
            expected_checkpoint_id,
            expected_history_fingerprint,
        )
    ):
        raise ValueError("EXACT_REVIEWED_CHECKPOINT_AND_HISTORY_HASH_PINS_REQUIRED")
    return (actual_checkpoint_id, actual_history_fingerprint) == (
        expected_checkpoint_id,
        expected_history_fingerprint,
    )


def observation_digest(value: object) -> str:
    """Only JSON-compatible DTO projection plus immutable byte leaves; no raw logging.

    Digest comparison is byte/hash consistency under SHA256, not authenticity.
    Callers pass asdict of ACTUAL native results, never decoded user DTOs as proof.
    """

    def encode(item: object) -> object:
        if item is None:
            return ["none"]
        if type(item) is bool:
            return ["bool", item]
        if type(item) is int:
            return ["int", item]
        if type(item) is float:
            return ["float", item]
        if isinstance(item, str):
            return ["str", item]
        if type(item) is bytes:
            return ["bytes", len(item), hashlib.sha256(item).hexdigest()]
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise TypeError("CHECKPOINT_OBSERVATION_STRING_KEYS_REQUIRED")
            return ["mapping", [[key, encode(item[key])] for key in sorted(item)]]
        if isinstance(item, (tuple, list)):
            return ["tuple" if type(item) is tuple else "list", [encode(x) for x in item]]
        raise TypeError("UNSUPPORTED_CHECKPOINT_OBSERVATION_VALUE")

    raw = json.dumps(encode(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()
