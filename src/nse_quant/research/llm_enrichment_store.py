"""Bounded persistence for LLM enrichment.

Stores enrichment-only metadata from the LLM enrichment adapter into a bounded
`llm_enrichment` table. This module never asserts event truth, never grants
decision eligibility, and never enables live trading.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from nse_quant.research.llm_enrichment import LLMEnrichmentSettings


class LLMEnrichmentStoreSettings(BaseModel):
    enabled: bool = False
    max_payload_bytes: int = Field(default=65536, ge=1)


def llm_enrichment_id(item: dict[str, Any], provider: str) -> str:
    canonical = json.dumps(
        {"item": item, "provider": provider},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


class LLMEnrichmentStore:
    def __init__(self, *, store: Any, settings: LLMEnrichmentStoreSettings) -> None:
        self._store = store
        self._settings = settings

    def persist(
        self,
        item: dict[str, Any],
        enrichment: dict[str, Any],
        settings: LLMEnrichmentSettings,
    ) -> dict[str, Any]:
        if not self._settings.enabled:
            return {
                "status": "REJECTED",
                "reason": "llm_enrichment_store_disabled",
                "decision_eligibility_asserted": False,
            }

        if not enrichment.get("available") or not enrichment.get("complete"):
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

        payload_bytes = len(
            json.dumps(
                {"item": item, "enrichment": enrichment},
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
        )
        if payload_bytes > self._settings.max_payload_bytes:
            return {
                "status": "REJECTED",
                "reason": "payload_too_large",
                "decision_eligibility_asserted": False,
            }

        provider = settings.provider
        identifier = llm_enrichment_id(item, provider)
        existing = self._store.conn.execute(
            "SELECT 1 FROM llm_enrichment WHERE enrichment_id = ?",
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
            INSERT INTO llm_enrichment VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                identifier,
                provider,
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
