"""Bounded persistence for offline news enrichment.

Stores enrichment-only metadata for reviewed news items. This module never
asserts event truth, never grants decision eligibility, and never enables live
trading.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from nse_quant.research.news_enrichment import NewsEnrichmentSettings


def enrichment_id(item: dict[str, Any]) -> str:
    canonical = json.dumps(
        item,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


class NewsEnrichmentStore:
    def __init__(self, *, store: Any, settings: NewsEnrichmentSettings) -> None:
        self._store = store
        self._settings = settings

    def persist(self, item: dict[str, Any], enrichment: dict[str, Any]) -> dict[str, Any]:
        if not self._settings.enabled:
            return {
                "status": "REJECTED",
                "reason": "news_enrichment_disabled",
                "decision_eligibility_asserted": False,
            }

        if not enrichment.get("available"):
            return {
                "status": "REJECTED",
                "reason": "enrichment_unavailable",
                "decision_eligibility_asserted": False,
            }

        headline = item.get("headline")
        if not isinstance(headline, str) or not headline.strip():
            return {
                "status": "REJECTED",
                "reason": "headline_required",
                "decision_eligibility_asserted": False,
            }

        identifier = enrichment_id(item)
        existing = self._store.conn.execute(
            "SELECT 1 FROM news_enrichment WHERE enrichment_id = ?",
            [identifier],
        ).fetchone()

        if existing:
            return {
                "status": "DUPLICATE",
                "enrichment_id": identifier,
                "decision_eligibility_asserted": False,
            }

        now = datetime.now().astimezone()
        self._store.conn.execute(
            """
            INSERT INTO news_enrichment VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                identifier,
                headline,
                json.dumps(enrichment.get("symbols", []), sort_keys=True, separators=(",", ":")),
                json.dumps(enrichment.get("topics", []), sort_keys=True, separators=(",", ":")),
                enrichment.get("sentiment"),
                enrichment.get("relevance_confidence"),
                json.dumps(enrichment, sort_keys=True, separators=(",", ":"), default=str),
                now,
            ],
        )

        return {
            "status": "INSERTED",
            "enrichment_id": identifier,
            "decision_eligibility_asserted": False,
        }
