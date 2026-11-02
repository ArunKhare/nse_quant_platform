"""Exact mapping of signed reference slots to unique reviewed source inputs."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceCoverage:
    status: str
    reason_codes: tuple[str, ...]
    expected_slots: tuple[str, ...]
    supplied_reference_keys: tuple[str, ...]
    binding_indices: tuple[int, ...]
    exact_coverage: bool


def plan_reference_coverage(
    expected_slots: tuple[str, ...],
    supplied_reference_keys: tuple[str, ...],
) -> ReferenceCoverage:
    """Hash keys identify full exact native pins, not authoritative source identities.

    Repeated signed slots are retained. More than one supplied source for a pin is
    ambiguous even if the caller says its bytes are identical. No first-source wins.
    """
    if (
        type(expected_slots) is not tuple
        or not 1 <= len(expected_slots) <= 64
        or type(supplied_reference_keys) is not tuple
        or len(supplied_reference_keys) > 64
        or any(
            not isinstance(x, str) or re.fullmatch(r"[a-f0-9]{64}", x) is None
            for x in expected_slots + supplied_reference_keys
        )
    ):
        raise ValueError("BOUNDED_IMMUTABLE_EXACT_REFERENCE_KEYS_REQUIRED")
    reasons: list[str] = []
    expected, supplied = set(expected_slots), set(supplied_reference_keys)
    if len(supplied) != len(supplied_reference_keys):
        reasons.append("AMBIGUOUS_DUPLICATE_REFERENCE_SOURCE")
    if expected - supplied:
        reasons.append("SIGNED_REFERENCE_SOURCE_MISSING")
    if supplied - expected:
        reasons.append("UNSIGNED_EXTRA_REFERENCE_SOURCE")
    indices = {
        key: index
        for index, key in enumerate(supplied_reference_keys)
        if supplied_reference_keys.count(key) == 1
    }
    return ReferenceCoverage(
        "exact_reference_coverage" if not reasons else "review_required",
        tuple(reasons) if reasons else ("ALL_SIGNED_REFERENCE_SLOTS_EXACTLY_COVERED",),
        expected_slots,
        supplied_reference_keys,
        tuple(indices.get(key, -1) for key in expected_slots),
        not reasons,
    )
