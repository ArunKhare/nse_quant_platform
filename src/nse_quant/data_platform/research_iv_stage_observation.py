"""Bounded digest/byte comparison; not stage, numerical or authority verification."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

VERSION = "research-iv-current-stage-observation@1"
MAX_NATIVE_BYTES = 167772160
MAX_ARTIFACT_BYTES = 4194304


@dataclass(frozen=True)
class IvStageObservationComparison:
    version: str
    first_matches_recorded_digest: bool
    second_matches_recorded_digest: bool
    native_observations_match: bool
    first_artifact_matches_pin: bool
    second_artifact_matches_pin: bool
    artifact_observations_match: bool
    all_observations_match: bool
    first_native_sha256: str
    second_native_sha256: str
    first_artifact_sha256: str
    second_artifact_sha256: str
    reason_codes: tuple[str, ...]
    evidence_fingerprint: str


def _pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def compare_iv_stage_observations(
    first_native: bytes,
    second_native: bytes,
    first_artifact: bytes,
    second_artifact: bytes,
    *,
    recorded_before_sha256: str,
    recorded_after_sha256: str,
    expected_bundle_id: str,
) -> IvStageObservationComparison:
    """Stage retains digests, not original full native DTO bytes. Never claim replay."""
    if (
        not all(
            _pin(value)
            for value in (
                recorded_before_sha256,
                recorded_after_sha256,
                expected_bundle_id,
            )
        )
        or recorded_before_sha256 != recorded_after_sha256
    ):
        raise ValueError("EXACT_UNCHANGED_IV_STAGE_RECORDED_PINS_REQUIRED")
    for raw, limit in (
        (first_native, MAX_NATIVE_BYTES),
        (second_native, MAX_NATIVE_BYTES),
        (first_artifact, MAX_ARTIFACT_BYTES),
        (second_artifact, MAX_ARTIFACT_BYTES),
    ):
        if type(raw) is not bytes or not 0 < len(raw) <= limit:
            raise ValueError("BOUNDED_IMMUTABLE_IV_STAGE_OBSERVATION_BYTES_REQUIRED")
    hashes = tuple(
        hashlib.sha256(raw).hexdigest()
        for raw in (
            first_native,
            second_native,
            first_artifact,
            second_artifact,
        )
    )
    one = hashes[0] == recorded_before_sha256
    two = hashes[1] == recorded_after_sha256
    native_stable = first_native == second_native
    artifact_one = hashes[2] == expected_bundle_id
    artifact_two = hashes[3] == expected_bundle_id
    artifact_stable = first_artifact == second_artifact
    flags = (one, two, native_stable, artifact_one, artifact_two, artifact_stable)
    codes = (
        "FIRST_CURRENT_IV_STAGE_NATIVE_DIGEST_DIFFERS",
        "SECOND_CURRENT_IV_STAGE_NATIVE_DIGEST_DIFFERS",
        "CURRENT_IV_STAGE_NATIVE_OBSERVATIONS_DIFFER",
        "FIRST_IV_STAGE_ARTIFACT_PIN_DIFFERS",
        "SECOND_IV_STAGE_ARTIFACT_PIN_DIFFERS",
        "IV_STAGE_ARTIFACT_OBSERVATIONS_DIFFER",
    )
    reasons = tuple(code for flag, code in zip(flags, codes, strict=True) if not flag)
    content = [
        VERSION,
        recorded_before_sha256,
        recorded_after_sha256,
        expected_bundle_id,
        hashes,
        flags,
        reasons,
    ]
    fingerprint = hashlib.sha256(
        json.dumps(
            content,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return IvStageObservationComparison(
        VERSION,
        one,
        two,
        native_stable,
        artifact_one,
        artifact_two,
        artifact_stable,
        all(flags),
        hashes[0],
        hashes[1],
        hashes[2],
        hashes[3],
        reasons,
        fingerprint,
    )
