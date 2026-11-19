"""Bounded exact byte comparison; never source, math, archive or authority verification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

VERSION = "research-iv-bundle-observation@1"
MAX_OBSERVATION_BYTES = 25165824


@dataclass(frozen=True)
class IvBundleObservationComparison:
    version: str
    recorded_matches_first: bool
    recorded_matches_second: bool
    fresh_observations_match: bool
    all_observations_match: bool
    recorded_sha256: str
    first_sha256: str
    second_sha256: str
    reason_codes: tuple[str, ...]
    evidence_fingerprint: str


def compare_iv_bundle_observations(
    recorded: bytes,
    first: bytes,
    second: bytes,
) -> IvBundleObservationComparison:
    """Exact bounded bytes only. Equal synthetic bytes do not prove a native result."""
    if any(
        type(raw) is not bytes or not 0 < len(raw) <= MAX_OBSERVATION_BYTES
        for raw in (recorded, first, second)
    ):
        raise ValueError("BOUNDED_IMMUTABLE_IV_BUNDLE_OBSERVATION_BYTES_REQUIRED")
    one, two, stable = recorded == first, recorded == second, first == second
    reasons: list[str] = []
    if not one:
        reasons.append("FIRST_CURRENT_IV_BUNDLE_DIFFERS_FROM_RECORDING")
    if not two:
        reasons.append("SECOND_CURRENT_IV_BUNDLE_DIFFERS_FROM_RECORDING")
    if not stable:
        reasons.append("CURRENT_IV_BUNDLE_OBSERVATIONS_DIFFER")
    hashes = tuple(hashlib.sha256(raw).hexdigest() for raw in (recorded, first, second))
    content = [VERSION, *hashes, one, two, stable, one and two and stable, reasons]
    fingerprint = hashlib.sha256(
        json.dumps(
            content,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return IvBundleObservationComparison(
        VERSION,
        one,
        two,
        stable,
        one and two and stable,
        hashes[0],
        hashes[1],
        hashes[2],
        tuple(reasons),
        fingerprint,
    )
