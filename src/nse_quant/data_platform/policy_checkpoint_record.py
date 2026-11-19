"""Immutable local checkpoint records; hashes are not authenticated governance."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

VERSION = "policy-checkpoint-record@1"


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def series_id(policy_id: str, governance_key_sha256: str) -> str:
    if (
        not isinstance(policy_id, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}", policy_id) is None
        or not pin(governance_key_sha256)
    ):
        raise ValueError("EXACT_CHECKPOINT_SERIES_REQUIRED")
    return sha(canonical([VERSION, policy_id, governance_key_sha256]).encode())


@dataclass(frozen=True)
class CheckpointRecord:
    series_id: str
    previous_id: str | None
    anchor_sequence: int
    anchor_sha256: str
    tip_sequence: int
    tip_sha256: str
    denied_keys: tuple[str, ...]
    window_fingerprint: str

    def __post_init__(self) -> None:
        if (
            not all(
                pin(x)
                for x in (
                    self.series_id,
                    self.anchor_sha256,
                    self.tip_sha256,
                    self.window_fingerprint,
                )
            )
            or self.previous_id is not None
            and not pin(self.previous_id)
            or type(self.anchor_sequence) is not int
            or type(self.tip_sequence) is not int
            or not 1 <= self.anchor_sequence <= self.tip_sequence <= 2147483647
            or type(self.denied_keys) is not tuple
            or len(self.denied_keys) > 128
            or any(not pin(x) for x in self.denied_keys)
            or tuple(sorted(set(self.denied_keys))) != self.denied_keys
        ):
            raise ValueError("BOUNDED_EXACT_CHECKPOINT_RECORD_REQUIRED")

    @property
    def checkpoint_id(self) -> str:
        return sha(canonical([VERSION, asdict(self)]).encode())


def validate_extension(previous: CheckpointRecord | None, candidate: CheckpointRecord) -> None:
    """Genesis pin is caller reviewed; no inference of complete earlier history."""
    if type(candidate) is not CheckpointRecord:
        raise TypeError("TYPED_CHECKPOINT_RECORD_REQUIRED")
    CheckpointRecord(**asdict(candidate))
    if previous is None:
        if candidate.previous_id is not None:
            raise ValueError("CHECKPOINT_GENESIS_PREDECESSOR_NOT_EMPTY")
        return
    if type(previous) is not CheckpointRecord:
        raise TypeError("TYPED_CHECKPOINT_PREDECESSOR_REQUIRED")
    CheckpointRecord(**asdict(previous))
    if candidate.previous_id != previous.checkpoint_id or candidate.series_id != previous.series_id:
        raise ValueError("CHECKPOINT_EXPECTED_HEAD_OR_SERIES_MISMATCH")
    if (candidate.anchor_sequence, candidate.anchor_sha256) != (
        previous.tip_sequence,
        previous.tip_sha256,
    ):
        raise ValueError("CHECKPOINT_WINDOW_DOES_NOT_START_AT_RETAINED_HEAD")
    if candidate.tip_sequence <= previous.tip_sequence:
        raise ValueError("CHECKPOINT_ADVANCE_REQUIRED_OR_EXACT_RETRY")
    if not set(previous.denied_keys).issubset(candidate.denied_keys):
        raise ValueError("CHECKPOINT_RETAINED_DENIAL_REMOVAL")
