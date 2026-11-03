"""Canonical retained recovery-plan bytes. Offline integrity is not native truth."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

VERSION = "research-iv-recovery-capture-record@1"
SERVICE_VERSION = "research-iv-stage-recovery-reconciliation@1"
MAX_RECORD_BYTES = 270336
DENIALS = (
    "current_source_checked",
    "orphan_status_determined",
    "destructive_actions_authorized",
    "adoption_authorized",
    "retry_authorized",
    "recovery_execution_authorized",
    "publication_asserted",
    "decision_eligibility_asserted",
)
NULLS = ("canonical_contract_id", "event_ts", "published_at")
PLAN_FIELDS = frozenset(
    (
        *DENIALS,
        *NULLS,
        "version",
        "status",
        "reason_codes",
        "stage_build_id",
        "expected_stage_fingerprint",
        "inventory_before_fingerprint",
        "inventory_after_fingerprint",
        "entries",
        "evidence_fingerprint",
        "stage_recording_checked",
    )
)
DISPOSITIONS = frozenset(
    (
        "RECORDED_ARTIFACT_RETAIN",
        "BOUND_ARTIFACT_REVIEW",
        "OUTSIDE_REVIEWED_BINDING_OWNERSHIP_UNKNOWN",
        "UNRESOLVED_ENTRY_RETAIN_FOR_REVIEW",
    )
)


def pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("IV_RECOVERY_CAPTURE_DUPLICATE_KEY")
        result[key] = value
    return result


def _nonfinite(value: str) -> Any:
    raise ValueError("IV_RECOVERY_CAPTURE_NONFINITE_JSON")


def decode(raw: str) -> dict[str, Any]:
    if type(raw) is not str or not 0 < len(raw.encode()) <= MAX_RECORD_BYTES:
        raise ValueError("IV_RECOVERY_CAPTURE_RECORD_BYTE_LIMIT")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_nonfinite)
        if (
            type(value) is not dict
            or set(value) != {"version", "artifact_root", "plan"}
            or value["version"] != VERSION
            or canonical(value) != raw
            or type(value["artifact_root"]) is not str
            or not 0 < len(value["artifact_root"]) <= 2048
            or any(ord(c) < 32 for c in value["artifact_root"])
        ):
            raise ValueError("IV_RECOVERY_CAPTURE_EXACT_RECORD_REQUIRED")
        plan = value["plan"]
        if (
            type(plan) is not dict
            or set(plan) != PLAN_FIELDS
            or plan["version"] != SERVICE_VERSION
            or plan["status"] not in ("reconciled_retain_only", "review_required")
            or plan["stage_recording_checked"] is not True
            or any(plan[key] is not False for key in DENIALS)
            or any(plan[key] is not None for key in NULLS)
            or any(
                not pin(plan[key])
                for key in (
                    "stage_build_id",
                    "expected_stage_fingerprint",
                    "inventory_before_fingerprint",
                    "inventory_after_fingerprint",
                    "evidence_fingerprint",
                )
            )
            or len(canonical(plan).encode()) > 262144
        ):
            raise ValueError("IV_RECOVERY_CAPTURE_RESEARCH_PLAN_REQUIRED")
        reasons = plan["reason_codes"]
        if (
            type(reasons) is not list
            or not 1 <= len(reasons) <= 3
            or any(type(c) is not str for c in reasons)
        ):
            raise ValueError("IV_RECOVERY_CAPTURE_REASONS_REQUIRED")
        negative_codes = {
            "IV_RECOVERY_EVIDENCE_CHANGED",
            "IV_RECOVERY_BOUND_ARTIFACT_NOT_OBSERVED",
            "IV_RECOVERY_UNRESOLVED_ENTRIES_RETAIN",
        }
        positive = plan["status"] == "reconciled_retain_only"
        expected = {"IV_RECOVERY_RECONCILED_NOT_EXECUTION_AUTHORIZATION"}
        if len(set(reasons)) != len(reasons) or not set(reasons) <= (
            expected if positive else negative_codes
        ):
            raise ValueError("IV_RECOVERY_CAPTURE_REASON_CONTRACT")
        entries = plan["entries"]
        if type(entries) is not list or len(entries) > 256:
            raise ValueError("IV_RECOVERY_CAPTURE_ENTRY_LIMIT")
        names: list[str] = []
        for entry in entries:
            if (
                type(entry) is not dict
                or set(entry) != {"name_sha256", "disposition"}
                or not pin(entry["name_sha256"])
                or entry["disposition"] not in DISPOSITIONS
            ):
                raise ValueError("IV_RECOVERY_CAPTURE_ENTRY_CONTRACT")
            names.append(entry["name_sha256"])
        if names != sorted(set(names)):
            raise ValueError("IV_RECOVERY_CAPTURE_SORTED_UNIQUE_ENTRIES_REQUIRED")
        if positive and (
            len(entries) != 1
            or entries[0]["disposition"] != "RECORDED_ARTIFACT_RETAIN"
            or plan["inventory_before_fingerprint"] != plan["inventory_after_fingerprint"]
        ):
            raise ValueError("IV_RECOVERY_CAPTURE_INCOMPLETE_POSITIVE")
        return value
    except (RecursionError, OverflowError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("IV_RECOVERY_CAPTURE_MALFORMED_JSON") from error


def encode(artifact_root: str, plan: dict[str, Any]) -> str:
    raw = canonical(dict(version=VERSION, artifact_root=artifact_root, plan=plan))
    decode(raw)
    return raw
