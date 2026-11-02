"""Small immutable research stage binding bytes; offline consistency is NOT native proof."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

VERSION = "research-iv-first-stage-record@1"
MAX_RECORD_BYTES = 8192
FLAGS = (
    "publication_asserted",
    "availability_evidence_verified",
    "historical_validity_asserted",
    "option_underlying_identity_binding_verified",
    "scenario_terms_authoritative",
    "model_suitability_verified",
    "source_acquisition_authenticity_asserted",
    "atomic_cross_database_snapshot_asserted",
    "decision_eligibility_asserted",
)
DEFINITION = (
    VERSION,
    "audited-research-iv-first-stage@1",
    "native-research-iv-artifact-materialization@1",
    "research-iv-bundle-current-source-revalidation@1",
    "research-iv-feature-bundle@1",
    "research-iv-artifact-files@1",
    "single-new-binding-no-retry-no-adoption@1",
)
FIELDS = frozenset(FLAGS) | {
    "version",
    "definition",
    "pins",
    "artifact_root",
    "artifact_name",
    "artifact_bytes",
    "before_sha256",
    "after_sha256",
    "status",
    "canonical_contract_id",
    "event_ts",
    "published_at",
}


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("IV_STAGE_DUPLICATE_KEY")
        result[key] = value
    return result


def _invalid(_value: str) -> Any:
    raise ValueError("IV_STAGE_NONFINITE_JSON")


def scope(pins: tuple[str, ...], artifact_root: str) -> str:
    if type(pins) is not tuple or len(pins) != 4 or not all(pin(value) for value in pins):
        raise ValueError("FOUR_EXACT_IV_STAGE_REVIEW_PINS_REQUIRED")
    if (
        type(artifact_root) is not str
        or not 0 < len(artifact_root) <= 2048
        or not Path(artifact_root).is_absolute()
        or ".." in Path(artifact_root).parts
        or any(ord(char) < 32 for char in artifact_root)
    ):
        raise ValueError("BOUNDED_ABSOLUTE_IV_STAGE_ROOT_REQUIRED")
    return sha(canonical([VERSION, list(pins), artifact_root]).encode())


def decode(raw: str) -> dict[str, Any]:
    if type(raw) is not str or not 0 < len(raw.encode()) <= MAX_RECORD_BYTES:
        raise ValueError("IV_STAGE_RECORD_BYTE_LIMIT")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid)
        if not isinstance(value, dict) or set(value) != FIELDS or canonical(value) != raw:
            raise ValueError("IV_STAGE_EXACT_CANONICAL_SCHEMA_REQUIRED")
        if (
            value["version"] != VERSION
            or value["definition"] != list(DEFINITION)
            or value["status"] != "RESEARCH_IV_STAGE_RECORDED_NOT_PUBLISHED"
            or type(value["pins"]) is not list
            or any(value[key] is not False for key in FLAGS)
            or any(
                value[key] is not None
                for key in (
                    "canonical_contract_id",
                    "event_ts",
                    "published_at",
                )
            )
            or type(value["artifact_bytes"]) is not int
            or not 1 <= value["artifact_bytes"] <= 4194304
            or not pin(value["before_sha256"])
            or value["before_sha256"] != value["after_sha256"]
        ):
            raise ValueError("IV_STAGE_RESEARCH_BINDING_CONTRACT_MISMATCH")
        scope(tuple(value["pins"]), value["artifact_root"])
        if value["artifact_name"] != value["pins"][2] + ".research-iv.json":
            raise ValueError("IV_STAGE_ARTIFACT_NAME_MISMATCH")
    except (UnicodeError, RecursionError, OverflowError, json.JSONDecodeError):
        raise ValueError("IV_STAGE_MALFORMED_JSON") from None
    return value


def build_id(raw: str) -> str:
    decode(raw)
    return sha(raw.encode())
