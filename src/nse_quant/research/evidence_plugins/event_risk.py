"""Look-ahead-safe scheduled-event risk evidence."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from nse_quant.research.evidence_plugins.base import (
    DecisionContext,
    EvidencePlugin,
)


class EventRiskPlugin(EvidencePlugin):
    name = "event_risk"

    def __init__(self, *, store: Any, settings: Any) -> None:
        self._store = store
        self._settings = settings

    def build(self, context: DecisionContext) -> dict[str, Any]:
        as_of = context.ts
        symbol = context.symbol
        rows = self._store.conn.execute(
            """
            SELECT
                event_id,
                event_type,
                event_ts,
                importance,
                affected_underlyings
            FROM market_events
            WHERE event_ts >= ?
              AND event_ts <= ?
            ORDER BY event_ts
            """,
            [
                as_of,
                as_of + timedelta(minutes=self._settings.blackout_minutes_before),
            ],
        ).fetchall()

        relevant_events: list[tuple[Any, ...]] = []

        for row in rows:
            affected_symbols = self._affected_symbols(row[4])

            if symbol not in affected_symbols:
                continue

            relevant_events.append(row)

        blocking_events = [
            row for row in relevant_events if row[1] in self._settings.high_impact_types
        ]

        should_block = self._settings.block_new_entries and bool(blocking_events)

        return {
            "available": True,
            "complete": True,
            "as_of": as_of.isoformat(),
            "symbol": symbol,
            "events_considered": len(relevant_events),
            "relevant_events": [
                {
                    "event_id": row[0],
                    "event_type": row[1],
                    "event_ts": row[2].isoformat(),
                    "importance": row[3],
                }
                for row in relevant_events
            ],
            "blocking_events": len(blocking_events),
            "recommended_action": ("BLOCK_NEW_ENTRIES" if should_block else "OBSERVE"),
            "block_new_entries": should_block,
        }

    @staticmethod
    def _affected_symbols(raw: Any) -> set[str]:
        if raw is None:
            return set()

        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return set()
        else:
            payload = raw

        if payload is None:
            return set()

        if isinstance(payload, dict):
            return set(payload.keys())

        if isinstance(payload, list):
            return {item for item in payload if isinstance(item, str)}

        return set()
