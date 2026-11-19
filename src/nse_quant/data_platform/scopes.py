"""Explicit execution scopes: UTC half-open ranges and immutable input references."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class ExecutionScope:
    symbols: tuple[str, ...]
    start: datetime
    end: datetime
    input_snapshot_refs: tuple[str, ...] = ()
    run_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        utc_iso(self.start)
        utc_iso(self.end)
        if self.start >= self.end:
            raise ValueError("Scope must have start < end; end is exclusive")
        if not self.symbols:
            raise ValueError("At least one symbol is required")
        for values in (self.symbols, self.input_snapshot_refs, self.run_ids):
            if not isinstance(values, tuple):
                raise TypeError("Scope lists must be immutable tuples")
            if any(not value.strip() for value in values):
                raise ValueError("Scope identifiers must not be empty")
            if len(set(values)) != len(values):
                raise ValueError("Scope identifiers must not be duplicated")
        if any(symbol != symbol.strip().upper() for symbol in self.symbols):
            raise ValueError("Symbols must be trimmed uppercase identities")

    def as_dict(self) -> dict[str, object]:
        return {
            "symbols": sorted(self.symbols),
            "start_inclusive": utc_iso(self.start),
            "end_exclusive": utc_iso(self.end),
            "input_snapshot_refs": sorted(self.input_snapshot_refs),
            "run_ids": sorted(self.run_ids),
        }
