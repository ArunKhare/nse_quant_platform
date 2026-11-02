"""Exact immutable observation comparison; NOT source, audit or numerical verification."""

from __future__ import annotations

from dataclasses import dataclass

MAX_OBSERVATION_BYTES = 1048576


@dataclass(frozen=True)
class IvObservationComparison:
    recorded_matches_first: bool
    recorded_matches_second: bool
    fresh_observations_match: bool
    all_observations_match: bool
    reason_codes: tuple[str, ...]


def compare_iv_observations(
    recorded: bytes,
    first: bytes,
    second: bytes,
) -> IvObservationComparison:
    if any(
        type(raw) is not bytes or not 0 < len(raw) <= MAX_OBSERVATION_BYTES
        for raw in (recorded, first, second)
    ):
        raise ValueError("BOUNDED_IMMUTABLE_IV_OBSERVATION_BYTES_REQUIRED")
    one, two, stable = recorded == first, recorded == second, first == second
    reasons: list[str] = []
    if not one:
        reasons.append("FIRST_CURRENT_IV_RESULT_DIFFERS_FROM_RECORDING")
    if not two:
        reasons.append("SECOND_CURRENT_IV_RESULT_DIFFERS_FROM_RECORDING")
    if not stable:
        reasons.append("CURRENT_IV_OBSERVATIONS_DIFFER")
    return IvObservationComparison(one, two, stable, one and two and stable, tuple(reasons))
