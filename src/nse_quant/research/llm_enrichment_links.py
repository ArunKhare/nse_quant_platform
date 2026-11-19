"""Bounded LLM enrichment-to-event linkage.

Links LLM enrichment metadata to a reviewed market event within a configured
time window. This is research evidence only; it never asserts event truth,
never grants decision eligibility, and never enables live trading.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LLMEnrichmentLinkSettings(BaseModel):
    enabled: bool = False
    max_link_window_minutes: int = Field(default=60, ge=1)


def llm_link_id(
    *,
    enrichment_id: str,
    event_id: str,
    instrument: str,
) -> str:
    canonical = json.dumps(
        {
            "enrichment_id": enrichment_id,
            "event_id": event_id,
            "instrument": instrument,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


class LLMEnrichmentEventLinker:
    def __init__(self, *, store: Any, settings: LLMEnrichmentLinkSettings) -> None:
        self._store = store
        self._settings = settings

    def link(
        self,
        *,
        enrichment_id: str,
        event_id: str,
        instrument: str,
        event_ts: datetime,
        observed_at: datetime,
    ) -> dict[str, Any]:
        if not self._settings.enabled:
            return {
                "status": "REJECTED",
                "reason": "llm_enrichment_linking_disabled",
                "decision_eligibility_asserted": False,
            }

        if (
            abs((event_ts - observed_at).total_seconds())
            > self._settings.max_link_window_minutes * 60
        ):
            return {
                "status": "REJECTED",
                "reason": "link_window_exceeded",
                "decision_eligibility_asserted": False,
            }

        enrichment_exists = self._store.conn.execute(
            "SELECT 1 FROM llm_enrichment WHERE enrichment_id = ?",
            [enrichment_id],
        ).fetchone()
        if not enrichment_exists:
            return {
                "status": "REJECTED",
                "reason": "enrichment_not_found",
                "decision_eligibility_asserted": False,
            }

        event_exists = self._store.conn.execute(
            "SELECT 1 FROM market_events WHERE event_id = ?",
            [event_id],
        ).fetchone()
        if not event_exists:
            return {
                "status": "REJECTED",
                "reason": "event_not_found",
                "decision_eligibility_asserted": False,
            }

        identifier = llm_link_id(
            enrichment_id=enrichment_id,
            event_id=event_id,
            instrument=instrument,
        )
        existing = self._store.conn.execute(
            "SELECT 1 FROM llm_enrichment_event_links WHERE link_id = ?",
            [identifier],
        ).fetchone()
        if existing:
            return {
                "status": "DUPLICATE",
                "link_id": identifier,
                "decision_eligibility_asserted": False,
            }

        payload = {
            "enrichment_id": enrichment_id,
            "event_id": event_id,
            "instrument": instrument,
            "event_ts": event_ts.isoformat(),
            "observed_at": observed_at.isoformat(),
            "link_window_minutes": self._settings.max_link_window_minutes,
        }
        self._store.conn.execute(
            """
            INSERT INTO llm_enrichment_event_links VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                identifier,
                enrichment_id,
                event_id,
                instrument,
                datetime.now(observed_at.tzinfo),
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ],
        )

        return {
            "status": "LINKED",
            "link_id": identifier,
            "decision_eligibility_asserted": False,
        }
