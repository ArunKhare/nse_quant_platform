"""Bounded event-reaction observation capture.

Records observed market reactions after a scheduled event. This is research
evidence, not event truth, execution authority, or a decision gate.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EventReactionSettings(BaseModel):
    enabled: bool = False
    observation_windows: list[int] = Field(
        default_factory=lambda: [5, 15, 30, 60],
        min_length=1,
    )
    max_reactions: int = Field(default=1000, ge=1)

    @field_validator("observation_windows")
    @classmethod
    def validate_windows(cls, value: list[int]) -> list[int]:
        if any(window <= 0 for window in value):
            raise ValueError("event reaction windows must be positive")
        if len(value) != len(set(value)):
            raise ValueError("event reaction windows must not contain duplicates")
        return value


def _optional_delta(baseline: float | None, observed: float | None) -> float | None:
    if baseline is None or observed is None:
        return None
    return observed - baseline


def build_event_reaction(
    *,
    baseline: dict[str, Any],
    observed: dict[str, Any],
    window_minutes: int,
) -> dict[str, Any]:
    baseline_spot = baseline.get("spot")
    observed_spot = observed.get("spot")

    spot_return_pct = None
    if (
        isinstance(baseline_spot, (int, float))
        and isinstance(observed_spot, (int, float))
        and baseline_spot > 0
    ):
        spot_return_pct = (observed_spot - baseline_spot) / baseline_spot * 100.0

    observed_high = observed.get("high")
    observed_low = observed.get("low")
    realized_range = (
        observed_high - observed_low
        if isinstance(observed_high, (int, float)) and isinstance(observed_low, (int, float))
        else None
    )

    return {
        "available": spot_return_pct is not None,
        "complete": all(
            observed.get(field) is not None
            for field in ("spot", "high", "low", "atm_iv", "expected_move_points", "pcr")
        ),
        "window_minutes": window_minutes,
        "spot_return_pct": spot_return_pct,
        "realized_range_points": realized_range,
        "atm_iv_change": _optional_delta(baseline.get("atm_iv"), observed.get("atm_iv")),
        "expected_move_change_points": _optional_delta(
            baseline.get("expected_move_points"),
            observed.get("expected_move_points"),
        ),
        "pcr_change": _optional_delta(baseline.get("pcr"), observed.get("pcr")),
        "relevant_oi_change": _optional_delta(
            baseline.get("relevant_oi"), observed.get("relevant_oi")
        ),
        "option_spread_change_pct": _optional_delta(
            baseline.get("option_spread_pct"),
            observed.get("option_spread_pct"),
        ),
    }


class EventReactionRecorder:
    """Persist one bounded post-event market-reaction observation."""

    def __init__(self, *, store: Any, settings: EventReactionSettings) -> None:
        self._store = store
        self._settings = settings

    def record(
        self,
        *,
        event_id: str,
        instrument: str,
        event_ts: datetime,
        window_minutes: int,
        baseline: dict[str, Any],
        observed: dict[str, Any],
        observed_at: datetime,
    ) -> dict[str, Any]:
        if window_minutes not in self._settings.observation_windows:
            raise ValueError(f"event reaction window {window_minutes} is not configured")

        reaction = build_event_reaction(
            baseline=baseline,
            observed=observed,
            window_minutes=window_minutes,
        )
        reaction_id = hashlib.sha256(
            json.dumps(
                {
                    "event_id": event_id,
                    "instrument": instrument,
                    "event_ts": event_ts.isoformat(),
                    "window_minutes": window_minutes,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
        ).hexdigest()

        self._store.conn.execute(
            """
            INSERT OR REPLACE INTO event_reactions VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                reaction_id,
                event_id,
                instrument,
                event_ts,
                window_minutes,
                observed_at,
                reaction["spot_return_pct"],
                reaction["realized_range_points"],
                reaction["atm_iv_change"],
                reaction["expected_move_change_points"],
                reaction["pcr_change"],
                reaction["relevant_oi_change"],
                reaction["option_spread_change_pct"],
                json.dumps(reaction, sort_keys=True, separators=(",", ":")),
                datetime.now(observed_at.tzinfo or observed_at.tzinfo),
            ],
        )
        return {"reaction_id": reaction_id, **reaction}
