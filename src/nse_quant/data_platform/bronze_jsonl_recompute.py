"""Independent strict JSONL-envelope recomputation; not publisher or identity authentication."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

VERSION = "bronze-jsonl-envelope-recompute@1"
COMMAND = "ingest.bronze_events@1"
CONFIG_HASH = hashlib.sha256(
    b"bronze-envelope-v1;10000-events;1MiB-payload;16MiB-artifact"
).hexdigest()
MAX_ARTIFACT_BYTES = 16777216
MAX_PLAN_BYTES = 65536
MAX_LINE_BYTES = 1500000
MAX_EVENTS = 64
MAX_PAYLOAD_BYTES = 1048576
MAX_TOTAL_PAYLOAD_BYTES = 8388608
REQUIRED = frozenset(
    {
        "envelope_version",
        "source",
        "capture_session_id",
        "source_record_id",
        "received_at",
        "payload_base64",
        "payload_format",
        "origin_kind",
    }
)
OPTIONAL = frozenset({"exchange_ts", "provider_event_id", "instrument_ref"})
PLAN_KEYS = frozenset(
    {
        "kind",
        "version",
        "input_hash",
        "batch_key",
        "events",
        "sources",
        "capture_sessions",
        "target_db",
        "actor",
        "code_revision",
        "initialize",
    }
)


class JsonlRecomputeRejected(ValueError):
    """Unsupported/malformed evidence, not a provider or identity rejection."""


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise JsonlRecomputeRejected("JSONL_DUPLICATE_KEY")
            result[key] = value
        return result

    def invalid(_value: str) -> Any:
        raise JsonlRecomputeRejected("JSONL_NONFINITE_VALUE")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def text(value: object, limit: int = 4096) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value.encode("utf-8")) <= limit
        and value == value.strip()
        and not any(ord(c) < 32 for c in value)
    )


def hash_pin(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def clock(value: object) -> str:
    if not isinstance(value, str):
        raise JsonlRecomputeRejected("JSONL_TIMESTAMP_STRING_REQUIRED")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise JsonlRecomputeRejected("JSONL_AWARE_TIMESTAMP_REQUIRED")
    return parsed.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class RecomputedEnvelope:
    capture_event_id: str
    envelope_hash: str
    payload_hash: str
    envelope_json: str
    payload: bytes = field(repr=False)


@dataclass(frozen=True)
class JsonlArtifact:
    version: str
    artifact_hash: str
    envelopes: tuple[RecomputedEnvelope, ...]


@dataclass(frozen=True)
class JsonlImportPlan:
    plan_sha256: str
    plan_json: str


def recompute_jsonl(raw: bytes) -> JsonlArtifact:
    """New strict subset of native envelope-v1; NEVER changes historical parser @1."""
    if not isinstance(raw, bytes) or len(raw) > MAX_ARTIFACT_BYTES:
        raise JsonlRecomputeRejected("JSONL_ARTIFACT_BYTE_LIMIT")
    result: list[RecomputedEnvelope] = []
    seen: set[str] = set()
    total_payload = 0
    try:
        for line in raw.decode("utf-8").splitlines():
            if not line.strip():
                continue
            if len(line.encode()) > MAX_LINE_BYTES or len(result) >= MAX_EVENTS:
                raise JsonlRecomputeRejected("JSONL_LINE_OR_EVENT_LIMIT")
            item = strict_json(line)
            if (
                not isinstance(item, dict)
                or not REQUIRED.issubset(item)
                or set(item) - REQUIRED - OPTIONAL
            ):
                raise JsonlRecomputeRejected("JSONL_ENVELOPE_SCHEMA_MISMATCH")
            if type(item["envelope_version"]) is not int or item["envelope_version"] != 1:
                raise JsonlRecomputeRejected("JSONL_ENVELOPE_VERSION_NOT_SUPPORTED")
            if any(
                not text(item[k])
                for k in (
                    "source",
                    "capture_session_id",
                    "source_record_id",
                    "payload_format",
                    "origin_kind",
                )
            ):
                raise JsonlRecomputeRejected("JSONL_IDENTIFIER_INVALID")
            if item["origin_kind"] not in {"live_provider", "historical_import", "legacy_snapshot"}:
                raise JsonlRecomputeRejected("JSONL_ORIGIN_KIND_NOT_SUPPORTED")
            for key in ("provider_event_id", "instrument_ref"):
                if item.get(key) is not None and not text(item[key]):
                    raise JsonlRecomputeRejected("JSONL_OPTIONAL_IDENTIFIER_INVALID")
            if not isinstance(item["payload_base64"], str):
                raise JsonlRecomputeRejected("JSONL_BASE64_STRING_REQUIRED")
            payload = base64.b64decode(item["payload_base64"], validate=True)
            total_payload += len(payload)
            if len(payload) > MAX_PAYLOAD_BYTES or total_payload > MAX_TOTAL_PAYLOAD_BYTES:
                raise JsonlRecomputeRejected("JSONL_DECODED_PAYLOAD_LIMIT")
            event_id = sha(
                canonical(
                    [item[k] for k in ("source", "capture_session_id", "source_record_id")]
                ).encode()
            )
            if event_id in seen:
                raise JsonlRecomputeRejected("JSONL_DUPLICATE_RECEIPT_ID_NOT_FRESH_BATCH")
            seen.add(event_id)
            envelope = {
                "envelope_version": 1,
                "source": item["source"],
                "capture_session_id": item["capture_session_id"],
                "source_record_id": item["source_record_id"],
                "received_at": clock(item["received_at"]),
                "payload_hash": sha(payload),
                "payload_format": item["payload_format"],
                "origin_kind": item["origin_kind"],
                "exchange_ts": (
                    clock(item["exchange_ts"]) if item.get("exchange_ts") is not None else None
                ),
                "provider_event_id": item.get("provider_event_id"),
                "instrument_ref": item.get("instrument_ref"),
            }
            encoded = canonical(envelope)
            result.append(
                RecomputedEnvelope(event_id, sha(encoded.encode()), sha(payload), encoded, payload)
            )
        if not result:
            raise JsonlRecomputeRejected("JSONL_EMPTY_ARTIFACT")
    except JsonlRecomputeRejected:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        raise JsonlRecomputeRejected("JSONL_ARTIFACT_MALFORMED") from None
    return JsonlArtifact(VERSION, sha(raw), tuple(result))


def decode_import_plan(raw: bytes, *, expected_plan_sha256: str) -> JsonlImportPlan:
    if (
        not isinstance(raw, bytes)
        or len(raw) > MAX_PLAN_BYTES
        or not hash_pin(expected_plan_sha256)
    ):
        raise JsonlRecomputeRejected("JSONL_BOUNDED_EXACT_PLAN_REQUIRED")
    if sha(raw) != expected_plan_sha256:
        raise JsonlRecomputeRejected("JSONL_PLAN_HASH_MISMATCH")
    try:
        value = strict_json(raw.decode("utf-8"))
        if (
            not isinstance(value, dict)
            or set(value) != PLAN_KEYS
            or canonical(value).encode() != raw
        ):
            raise JsonlRecomputeRejected("JSONL_PLAN_SCHEMA_OR_CANONICAL_MISMATCH")
        if (
            value["kind"] != "bronze_event_import"
            or type(value["version"]) is not int
            or value["version"] != 1
            or type(value["initialize"]) is not bool
            or type(value["events"]) is not int
            or not 1 <= value["events"] <= MAX_EVENTS
            or not hash_pin(value["input_hash"])
            or any(not text(value[k]) for k in ("batch_key", "target_db", "actor", "code_revision"))
        ):
            raise JsonlRecomputeRejected("JSONL_PLAN_VALUES_NOT_SUPPORTED")
        for key in ("sources", "capture_sessions"):
            items = value[key]
            if (
                not isinstance(items, list)
                or not 1 <= len(items) <= MAX_EVENTS
                or any(not text(item) for item in items)
                or items != sorted(set(items))
            ):
                raise JsonlRecomputeRejected("JSONL_PLAN_SOURCE_IDENTITIES_INVALID")
        return JsonlImportPlan(expected_plan_sha256, raw.decode("utf-8"))
    except JsonlRecomputeRejected:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        raise JsonlRecomputeRejected("JSONL_PLAN_MALFORMED") from None


def verify_plan_inputs(
    plan: JsonlImportPlan,
    artifact: JsonlArtifact,
    *,
    batch_key: str,
    actor_id: str,
    code_revision: str,
) -> None:
    value = strict_json(plan.plan_json)
    envelopes = [strict_json(event.envelope_json) for event in artifact.envelopes]
    expected = (
        artifact.artifact_hash,
        batch_key,
        len(envelopes),
        sorted({event["source"] for event in envelopes}),
        sorted({event["capture_session_id"] for event in envelopes}),
        actor_id,
        code_revision,
    )
    actual = tuple(
        value[k]
        for k in (
            "input_hash",
            "batch_key",
            "events",
            "sources",
            "capture_sessions",
            "actor",
            "code_revision",
        )
    )
    if canonical(actual) != canonical(expected):
        raise JsonlRecomputeRejected("JSONL_PLAN_INPUT_OR_ACTOR_BINDING_MISMATCH")
