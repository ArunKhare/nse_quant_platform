"""Exact bounded retained/native stress envelope comparison, not independent verification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

VERSION = "research-iv-stress-archive-observation@1"
MAX_OBSERVATION_BYTES = 25165824


@dataclass(frozen=True)
class IvStressArchiveComparison:
    version: str
    first_matches_recording: bool
    second_matches_recording: bool
    current_observations_match: bool
    all_observations_match: bool
    recorded_sha256: str
    first_sha256: str
    second_sha256: str
    reason_codes: tuple[str, ...]
    evidence_fingerprint: str


def compare_iv_stress_archive_observations(
    recorded: bytes,
    first: bytes,
    second: bytes,
) -> IvStressArchiveComparison:
    """Full byte equality, NOT IV-only, scalar hash-field or approximate agreement."""
    if any(
        type(raw) is not bytes or not 0 < len(raw) <= MAX_OBSERVATION_BYTES
        for raw in (recorded, first, second)
    ):
        raise ValueError("BOUNDED_IMMUTABLE_STRESS_ARCHIVE_OBSERVATIONS_REQUIRED")
    one, two, stable = first == recorded, second == recorded, first == second
    reasons = tuple(
        code
        for flag, code in (
            (one, "FIRST_CURRENT_STRESS_OBSERVATION_DIFFERS"),
            (two, "SECOND_CURRENT_STRESS_OBSERVATION_DIFFERS"),
            (stable, "CURRENT_STRESS_OBSERVATIONS_DIFFER"),
        )
        if not flag
    )
    hashes = tuple(hashlib.sha256(raw).hexdigest() for raw in (recorded, first, second))
    content = [VERSION, hashes, one, two, stable, reasons]
    fingerprint = hashlib.sha256(
        json.dumps(
            content,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return IvStressArchiveComparison(
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
