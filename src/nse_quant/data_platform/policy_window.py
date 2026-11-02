"""Bounded policy-window sequence constraints, not global chronology or authority."""

from __future__ import annotations

import re
from dataclasses import dataclass

VERSION = "observed-scope-policy-window@1"
MAX_OBSERVATIONS = 64


def _pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


@dataclass(frozen=True)
class PolicyPosition:
    sequence: int
    policy_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.sequence) is not int
            or not 1 <= self.sequence <= 2147483647
            or not _pin(self.policy_sha256)
        ):
            raise ValueError("EXACT_POLICY_SEQUENCE_AND_HASH_REQUIRED")


@dataclass(frozen=True)
class PolicyWindowEntry:
    policy_id: str
    position: PolicyPosition
    denied_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.policy_id, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}", self.policy_id) is None
            or type(self.position) is not PolicyPosition
            or type(self.denied_keys) is not tuple
            or len(self.denied_keys) > 128
            or any(not _pin(key) for key in self.denied_keys)
            or len(set(self.denied_keys)) != len(self.denied_keys)
        ):
            raise ValueError("BOUNDED_EXACT_POLICY_WINDOW_ENTRY_REQUIRED")
        PolicyPosition(self.position.sequence, self.position.policy_sha256)


@dataclass(frozen=True)
class PolicyWindowCheck:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    observed_sequences: tuple[int, ...]
    exact_retry_count: int
    window_constraints_satisfied: bool = False
    policy_currentness_verified: bool = False
    policy_authority_authenticated: bool = False
    authorized_key_reactivation_asserted: bool = False
    decision_eligibility_asserted: bool = False


def check_policy_window(
    entries: tuple[PolicyWindowEntry, ...],
    *,
    anchor: PolicyPosition,
    tip: PolicyPosition,
) -> PolicyWindowCheck:
    """Entries are in caller-observed order. Pure constraints, NOT signature verification.

    Signed @1 snapshots lack predecessor hashes. Contiguous sequence LABELS do not
    prove a publisher's causal chain, complete history or externally latest policy.
    """
    if (
        type(entries) is not tuple
        or not 1 <= len(entries) <= MAX_OBSERVATIONS
        or type(anchor) is not PolicyPosition
        or type(tip) is not PolicyPosition
    ):
        raise ValueError("BOUNDED_IMMUTABLE_POLICY_WINDOW_AND_ENDPOINTS_REQUIRED")
    anchor = PolicyPosition(anchor.sequence, anchor.policy_sha256)
    tip = PolicyPosition(tip.sequence, tip.policy_sha256)
    if tip.sequence < anchor.sequence:
        raise ValueError("POLICY_WINDOW_ENDPOINT_ORDER_INVALID")
    checked: list[PolicyWindowEntry] = []
    for item in entries:
        if type(item) is not PolicyWindowEntry:
            raise TypeError("TYPED_POLICY_WINDOW_ENTRY_REQUIRED")
        checked.append(PolicyWindowEntry(item.policy_id, item.position, item.denied_keys))
    reasons: list[str] = []
    if len({item.policy_id for item in checked}) != 1:
        reasons.append("POLICY_WINDOW_SERIES_MISMATCH")
    by_sequence: dict[int, str] = {}
    projections: dict[tuple[int, str], PolicyWindowEntry] = {}
    retries = 0
    previous: PolicyWindowEntry | None = None
    denied_seen: set[str] = set()
    for item in checked:
        seq, digest = item.position.sequence, item.position.policy_sha256
        position_key = (seq, digest)
        if position_key in projections and projections[position_key] != item:
            reasons.append("POLICY_WINDOW_SAME_PIN_PROJECTION_MISMATCH")
        projections[position_key] = item
        if seq in by_sequence:
            if by_sequence[seq] != digest:
                reasons.append("POLICY_WINDOW_SAME_SEQUENCE_FORK")
            else:
                retries += 1
        by_sequence[seq] = digest
        if previous is not None:
            if seq < previous.position.sequence:
                reasons.append("POLICY_WINDOW_OBSERVED_ROLLBACK")
            elif seq > previous.position.sequence + 1:
                reasons.append("POLICY_WINDOW_SEQUENCE_GAP")
        if not denied_seen.issubset(item.denied_keys):
            reasons.append("POLICY_WINDOW_DENIAL_REMOVAL_REQUIRES_NEW_CONTRACT")
        denied_seen.update(item.denied_keys)
        previous = item
    if checked[0].position != anchor:
        reasons.append("POLICY_WINDOW_ANCHOR_PIN_MISMATCH")
    if checked[-1].position != tip:
        reasons.append("POLICY_WINDOW_TIP_PIN_MISMATCH")
    reasons = list(dict.fromkeys(reasons))
    return PolicyWindowCheck(
        VERSION,
        "observed_window_consistent" if not reasons else "review_required",
        tuple(reasons) if reasons else ("EXACT_OBSERVED_WINDOW_CONSTRAINTS_SATISFIED",),
        tuple(item.position.sequence for item in checked),
        retries,
        not reasons,
    )
