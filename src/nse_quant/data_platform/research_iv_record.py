"""Exact bounded research-IV archive bytes and immutable input/result identities."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

VERSION = "research-iv-build-record@1"
MAX_RESULT_BYTES = 1048576
MAX_TERMS_BYTES = 4096


def pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("RESEARCH_IV_ARCHIVE_DUPLICATE_KEY")
        result[key] = value
    return result


def _invalid(_value: str) -> Any:
    raise ValueError("RESEARCH_IV_ARCHIVE_NONFINITE_JSON")


def checked_json(raw: str, limit: int = MAX_RESULT_BYTES) -> dict[str, Any]:
    if not isinstance(raw, str) or not 0 < len(raw.encode()) <= limit:
        raise ValueError("RESEARCH_IV_ARCHIVE_BYTE_LIMIT")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid)
        if not isinstance(value, dict) or canonical(value) != raw:
            raise ValueError("RESEARCH_IV_ARCHIVE_CANONICAL_OBJECT_REQUIRED")
    except (UnicodeError, RecursionError, OverflowError, json.JSONDecodeError):
        raise ValueError("RESEARCH_IV_ARCHIVE_MALFORMED_JSON") from None
    return value


def input_id(
    option_build_id: str, spot_build_id: str, terms_pin: str, definition_fingerprint: str
) -> str:
    if (
        not all(pin(x) for x in (option_build_id, spot_build_id, terms_pin, definition_fingerprint))
        or option_build_id == spot_build_id
    ):
        raise ValueError("EXACT_DISTINCT_RESEARCH_IV_INPUT_PINS_REQUIRED")
    return sha(
        canonical(
            [VERSION, option_build_id, spot_build_id, terms_pin, definition_fingerprint]
        ).encode()
    )


def build_id(group: str, result_json: str) -> str:
    if not pin(group):
        raise ValueError("EXACT_RESEARCH_IV_INPUT_GROUP_REQUIRED")
    checked_json(result_json)
    return sha(canonical([VERSION, group, sha(result_json.encode())]).encode())


def validate_prior_links(raw: str, expected: tuple[str, ...]) -> None:
    if (
        not isinstance(raw, str)
        or len(raw.encode()) > 32768
        or type(expected) is not tuple
        or len(expected) > 256
        or any(not pin(x) for x in expected)
        or len(set(expected)) != len(expected)
    ):
        raise ValueError("BOUNDED_RESEARCH_IV_HISTORY_LINKS_REQUIRED")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid)
    except (ValueError, TypeError, RecursionError):
        raise ValueError("RESEARCH_IV_HISTORY_LINKS_INVALID") from None
    if value != list(expected) or canonical(value) != raw:
        raise ValueError("RESEARCH_IV_ALL_PRIOR_HISTORY_LINKS_MISMATCH")
