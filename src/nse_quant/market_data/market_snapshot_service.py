"""Opt-in read boundary for one service-owned market snapshot slot."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from typing import Any

READ_SQL = "SELECT payload FROM market_snapshot_slot WHERE slot = 1"
MAX_BYTES = 1024 * 1024


class SnapshotUnavailable(ValueError):
    """No usable snapshot; callers must not fall back to local capture."""


def _clock(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise SnapshotUnavailable("naive_clock")
    return result


def read_snapshot(
    connection: Any, *, underlying: str, expected_tokens: frozenset[int], as_of: datetime, max_age: timedelta
) -> dict[str, Any]:
    """Use a caller-owned remote session. No fallback, writes, or cached result."""
    if as_of.utcoffset() is None or max_age <= timedelta(0) or not expected_tokens:
        raise ValueError("invalid_read_policy")
    try:
        rows = connection.execute(READ_SQL).fetchmany(2)
    except Exception:
        raise SnapshotUnavailable("service_unavailable") from None
    if not rows:
        raise SnapshotUnavailable("no_snapshot")
    try:
        if len(rows) != 1 or not isinstance(rows[0][0], str):
            raise SnapshotUnavailable("invalid_slot")
        raw = rows[0][0]
        if len(raw.encode()) > MAX_BYTES:
            raise SnapshotUnavailable("snapshot_size")
        result = json.loads(raw)
        if (
            result["version"] != 1
            or result["underlying"] != underlying
            or not isinstance(result["capture_id"], str)
            or not result["capture_id"].strip()
        ):
            raise SnapshotUnavailable("identity_mismatch")
        captured = _clock(result["captured_at"])
        spot = result["spot"]
        price = spot["price"]
        if type(price) not in (float, int) or not math.isfinite(price) or price <= 0:
            raise SnapshotUnavailable("invalid_spot")
        quotes = result["quotes"]
        tokens = [quote["token"] for quote in quotes]
        if (
            any(type(token) is not int for token in tokens)
            or len(tokens) != len(expected_tokens)
            or set(tokens) != expected_tokens
        ):
            raise SnapshotUnavailable("incomplete_chain")
        for quote in quotes:
            bid, ask = quote["bid"], quote["ask"]
            if any(type(x) not in (float, int) or not math.isfinite(x) for x in (bid, ask)) or not 0 < bid <= ask:
                raise SnapshotUnavailable("invalid_quote")
        for item in [spot, *quotes]:
            if item["capture_id"] != result["capture_id"]:
                raise SnapshotUnavailable("mixed_capture")
            source, received = _clock(item["source_time"]), _clock(item["received_at"])
            if not as_of - max_age <= source <= received <= captured <= as_of:
                raise SnapshotUnavailable("stale_future_or_unordered")
    except SnapshotUnavailable:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise SnapshotUnavailable("malformed_snapshot") from None
    return result
