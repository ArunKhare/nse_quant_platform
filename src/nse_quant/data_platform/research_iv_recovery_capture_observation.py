"""Bounded exact-byte comparison. This pure helper proves no native or audit truth."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

VERSION = "research-iv-recovery-capture-observation@1"
MAX_PLAN_BYTES = 262144


@dataclass(frozen=True)
class RecoveryCaptureComparison:
    version: str
    first_matches_recorded_plan: bool
    second_matches_recorded_plan: bool
    native_plans_match: bool
    all_plan_bytes_match: bool
    recorded_plan_sha256: str
    first_plan_sha256: str
    second_plan_sha256: str
    reason_codes: tuple[str, ...]
    evidence_fingerprint: str


def compare_recovery_capture_plans(
    recorded: bytes,
    first: bytes,
    second: bytes,
) -> RecoveryCaptureComparison:
    """Compare full retained plan DTO bytes, not its internal observation digests."""
    if any(
        type(raw) is not bytes or not 0 < len(raw) <= MAX_PLAN_BYTES
        for raw in (recorded, first, second)
    ):
        raise ValueError("IV_RECOVERY_CAPTURE_BOUNDED_PLAN_BYTES_REQUIRED")
    one, two, stable = first == recorded, second == recorded, first == second
    reasons = tuple(
        code
        for flag, code in (
            (one, "FIRST_RECOVERY_PLAN_DIFFERS_FROM_RECORDING"),
            (two, "SECOND_RECOVERY_PLAN_DIFFERS_FROM_RECORDING"),
            (stable, "CURRENT_RECOVERY_PLANS_DIFFER"),
        )
        if not flag
    )
    hashes = tuple(hashlib.sha256(raw).hexdigest() for raw in (recorded, first, second))
    core = [VERSION, hashes, one, two, stable, reasons]
    fingerprint = hashlib.sha256(
        json.dumps(
            core,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return RecoveryCaptureComparison(
        VERSION,
        one,
        two,
        stable,
        one and two and stable,
        hashes[0],
        hashes[1],
        hashes[2],
        reasons,
        fingerprint,
    )
