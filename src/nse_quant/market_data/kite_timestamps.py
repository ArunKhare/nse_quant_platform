"""Timestamp normalization for Kite REST quote responses."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nse_quant.core.constants import IST


def normalize_kite_rest_timestamp(
    value: Any,
    *,
    field: str,
) -> datetime | None:
    """Interpret naive Kite REST wall-clock timestamps as Asia/Kolkata."""
    if value is None:
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid Kite REST timestamp for {field}: {value!r}") from exc
    else:
        raise ValueError(
            f"Unsupported Kite REST timestamp type for {field}: {type(value).__name__}"
        )

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=IST)

    return parsed.astimezone(UTC)
