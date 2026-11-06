"""Look-ahead-safe event-to-instrument impact mapping evidence."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from nse_quant.research.evidence_plugins.base import (
    DecisionContext,
    EvidencePlugin,
)


class EventImpactMapper(EvidencePlugin):
    """Map reviewed scheduled events to instrument-level impact evidence.

    This is retained observational evidence, not event truth, execution
    authority, or a decision-eligibility grant.
    """

    name = "event_impact"

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
                affected_underlyings,
                surprise_label
            FROM market_events
            WHERE event_ts >= ?
                AND event_ts <= ?
                AND ingested_at <= ?
            ORDER BY event_ts, event_id
            """,
            [
                as_of - timedelta(minutes=self._settings.blackout_minutes_after),
                as_of + timedelta(minutes=self._settings.blackout_minutes_before),
                as_of,
            ],
        ).fetchall()

        mappings: list[dict[str, Any]] = []
        incomplete = False

        for row in rows:
            affected = self._affected(row[4])
            if affected is None:
                incomplete = True
                continue
            if symbol not in affected:
                continue
            detail = affected[symbol] if isinstance(affected, dict) else {}
            mappings.append(
                {
                    "event_id": row[0],
                    "event_type": row[1],
                    "event_ts": row[2].isoformat(),
                    "importance": row[3],
                    "surprise_label": row[5],
                    "instrument": symbol,
                    "direction": self._text(detail, "direction"),
                    "volatility_impact": self._text(detail, "volatility_impact"),
                    "liquidity_impact": self._text(detail, "liquidity_impact"),
                    "confidence": self._confidence(detail),
                    "recommended_action": "OBSERVE",
                }
            )

        return {
            "available": True,
            "complete": not incomplete,
            "as_of": as_of.isoformat(),
            "symbol": symbol,
            "events_considered": len(rows),
            "mapped_events": len(mappings),
            "instrument_mappings": mappings,
            "recommended_action": "OBSERVE",
            "block_new_entries": False,
            "decision_eligibility_asserted": False,
        }

    @staticmethod
    def _affected(raw: Any) -> dict[str, Any] | list[str] | None:
        if raw is None:
            return {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
            return {item: {} for item in raw}
        return None

    @staticmethod
    def _text(detail: Any, key: str) -> str | None:
        if not isinstance(detail, dict):
            return None
        value = detail.get(key)
        return value if isinstance(value, str) else None

    @staticmethod
    def _confidence(detail: Any) -> float | None:
        if not isinstance(detail, dict):
            return None
        value = detail.get("confidence")
        if isinstance(value, (int, float)) and 0.0 <= float(value) <= 1.0:
            return float(value)
        return None
