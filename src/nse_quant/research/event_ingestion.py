"""Bounded event ingestion service.

Persists reviewed scheduled-event records into `market_events`. This service
never asserts event truth, never grants decision eligibility, and never enables
live trading.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class EventIngestionSettings(BaseModel):
    enabled: bool = False
    allowed_sources: list[str] = Field(default_factory=list)
    max_payload_bytes: int = Field(default=65536, ge=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> EventIngestionSettings:
        if any(not source.strip() for source in self.allowed_sources):
            raise ValueError("event ingestion sources must be non-empty")
        return self


REQUIRED_FIELDS = (
    "event_id",
    "source",
    "event_type",
    "event_ts",
    "importance",
    "affected_underlyings",
)


class EventIngestionService:
    def __init__(self, *, store: Any, settings: EventIngestionSettings) -> None:
        self._store = store
        self._settings = settings

    def ingest(self, event: dict[str, Any]) -> dict[str, Any]:
        if not self._settings.enabled:
            return {
                "status": "REJECTED",
                "reason": "event_ingestion_disabled",
                "decision_eligibility_asserted": False,
            }

        missing = [field for field in REQUIRED_FIELDS if event.get(field) is None]
        if missing:
            return {
                "status": "REJECTED",
                "reason": "missing_required_fields",
                "missing": missing,
                "decision_eligibility_asserted": False,
            }

        source = event["source"]
        if source not in self._settings.allowed_sources:
            return {
                "status": "REJECTED",
                "reason": "source_not_allowed",
                "decision_eligibility_asserted": False,
            }

        event_ts = event["event_ts"]
        if not isinstance(event_ts, datetime) or event_ts.tzinfo is None:
            return {
                "status": "REJECTED",
                "reason": "aware_event_timestamp_required",
                "decision_eligibility_asserted": False,
            }

        payload_bytes = len(
            json.dumps(event, sort_keys=True, separators=(",", ":"), default=str).encode()
        )
        if payload_bytes > self._settings.max_payload_bytes:
            return {
                "status": "REJECTED",
                "reason": "payload_too_large",
                "decision_eligibility_asserted": False,
            }

        affected = event["affected_underlyings"]
        if not isinstance(affected, (list, dict)):
            return {
                "status": "REJECTED",
                "reason": "affected_underlyings_must_be_list_or_object",
                "decision_eligibility_asserted": False,
            }

        existing = self._store.conn.execute(
            "SELECT 1 FROM market_events WHERE event_id = ?",
            [event["event_id"]],
        ).fetchone()

        if existing:
            return {
                "status": "DUPLICATE",
                "event_id": event["event_id"],
                "decision_eligibility_asserted": False,
            }

        self._store.conn.execute(
            """
            INSERT INTO market_events VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                event["event_id"],
                source,
                event["event_type"],
                event.get("title"),
                event.get("description"),
                event.get("symbol"),
                event_ts,
                event["importance"],
                event.get("consensus_value"),
                event.get("actual_value"),
                event.get("surprise_label"),
                json.dumps(affected, sort_keys=True, separators=(",", ":")),
                json.dumps(event, sort_keys=True, separators=(",", ":"), default=str),
                datetime.now(event_ts.tzinfo),
            ],
        )

        return {
            "status": "INSERTED",
            "event_id": event["event_id"],
            "decision_eligibility_asserted": False,
        }
