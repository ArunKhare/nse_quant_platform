"""Bounded event-risk plugin.

Queries reviewed market events in a look-ahead-safe window and synthesizes
observational event-risk evidence. This plugin never asserts event truth,
never grants decision eligibility, and never enables live trading.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, model_validator


class EventRiskSettings(BaseModel):
    enabled: bool = False
    block_new_entries: bool = False
    blackout_minutes_before: int = Field(default=30, ge=1)
    blackout_minutes_after: int = Field(default=30, ge=1)
    allowed_event_types: list[str] = Field(default_factory=list)
    max_events: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> EventRiskSettings:
        if any(not event_type.strip() for event_type in self.allowed_event_types):
            raise ValueError("event types must be non-empty")
        return self


def impact_id(
    *,
    run_id: str,
    event_id: str,
    instrument: str,
    decision_ts: datetime,
) -> str:
    canonical = json.dumps(
        {
            "run_id": run_id,
            "event_id": event_id,
            "instrument": instrument,
            "decision_ts": decision_ts.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


class EventRiskPlugin:
    def __init__(self, *, store: Any, settings: EventRiskSettings) -> None:
        self._store = store
        self._settings = settings

    def evaluate(
        self,
        *,
        run_id: str,
        instrument: str,
        decision_ts: datetime,
    ) -> dict[str, Any]:
        if not self._settings.enabled:
            return {
                "available": False,
                "complete": False,
                "reason": "event_risk_disabled",
                "decision_eligibility_asserted": False,
            }

        if decision_ts.tzinfo is None:
            return {
                "available": False,
                "complete": False,
                "reason": "aware_decision_timestamp_required",
                "decision_eligibility_asserted": False,
            }

        start = decision_ts - timedelta(minutes=self._settings.blackout_minutes_before)
        end = decision_ts + timedelta(minutes=self._settings.blackout_minutes_after)

        rows = self._store.conn.execute(
            """
            SELECT event_id, event_type, importance, affected_underlyings
            FROM market_events
            WHERE event_ts >= ? AND event_ts <= ?
              AND event_type IN (SELECT unnest(?))
            LIMIT ?
            """,
            [start, end, self._settings.allowed_event_types, self._settings.max_events],
        ).fetchall()

        matched = []
        blocked = False
        for event_id, event_type, importance, affected in rows:
            affected_list = json.loads(affected) if isinstance(affected, str) else affected
            if instrument not in affected_list:
                continue
            confidence = 0.85 if importance == "high" else 0.5
            action = (
                "BLOCK_NEW_ENTRIES"
                if self._settings.block_new_entries and importance == "high"
                else "OBSERVE"
            )
            if action == "BLOCK_NEW_ENTRIES":
                blocked = True
            identifier = impact_id(
                run_id=run_id,
                event_id=event_id,
                instrument=instrument,
                decision_ts=decision_ts,
            )
            payload = {
                "plugin": "event_risk",
                "available": True,
                "event_id": event_id,
                "event_type": event_type,
                "instrument": instrument,
                "decision_ts": decision_ts.isoformat(),
                "direction": "CONDITIONAL",
                "volatility_impact": "HIGH",
                "liquidity_impact": "MEDIUM",
                "confidence": confidence,
                "recommended_action": action,
                "reason": "high_impact_event_within_blackout_window",
            }
            self._store.conn.execute(
                """
                INSERT INTO event_impact_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    identifier,
                    run_id,
                    decision_ts,
                    event_id,
                    event_type,
                    instrument,
                    "CONDITIONAL",
                    "HIGH",
                    "MEDIUM",
                    confidence,
                    action,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ],
            )
            matched.append(payload)

        return {
            "available": True,
            "complete": True,
            "event_risk": {
                "blocked_new_entries": blocked,
                "matched_events": len(matched),
                "evidence": matched,
            },
            "decision_eligibility_asserted": False,
        }
