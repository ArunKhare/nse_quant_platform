"""Bounded LLM enrichment adapter.

Produces enrichment-only metadata for reviewed news items using an injected
callable. This module never asserts event truth, never grants decision
eligibility, and never enables live trading.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, model_validator


class LLMEnrichmentSettings(BaseModel):
    enabled: bool = False
    provider: str = "manual"
    max_headline_length: int = Field(default=512, ge=1)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    allowed_symbols: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_bounds(self) -> LLMEnrichmentSettings:
        if any(not symbol.strip() for symbol in self.allowed_symbols):
            raise ValueError("allowed symbols must be non-empty")
        return self


class LLMEnrichmentAdapter:
    def __init__(
        self,
        *,
        settings: LLMEnrichmentSettings,
        enricher: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self._settings = settings
        self._enricher = enricher

    def enrich(self, item: dict[str, Any]) -> dict[str, Any]:
        if not self._settings.enabled:
            return {
                "available": False,
                "complete": False,
                "reason": "llm_enrichment_disabled",
                "enrichment_only": True,
                "decision_eligibility_asserted": False,
            }

        headline = item.get("headline")
        if not isinstance(headline, str) or not headline.strip():
            return {
                "available": False,
                "complete": False,
                "reason": "headline_required",
                "enrichment_only": True,
                "decision_eligibility_asserted": False,
            }

        if len(headline) > self._settings.max_headline_length:
            return {
                "available": False,
                "complete": False,
                "reason": "headline_too_long",
                "enrichment_only": True,
                "decision_eligibility_asserted": False,
            }

        if self._enricher is None:
            return {
                "available": False,
                "complete": False,
                "reason": "enricher_not_configured",
                "enrichment_only": True,
                "decision_eligibility_asserted": False,
            }

        raw = self._enricher(item)
        if not isinstance(raw, dict):
            return {
                "available": False,
                "complete": False,
                "reason": "enricher_output_invalid",
                "enrichment_only": True,
                "decision_eligibility_asserted": False,
            }

        symbols = raw.get("symbols", [])
        if not isinstance(symbols, list):
            return {
                "available": False,
                "complete": False,
                "reason": "symbols_must_be_list",
                "enrichment_only": True,
                "decision_eligibility_asserted": False,
            }

        filtered_symbols = [
            symbol
            for symbol in symbols
            if isinstance(symbol, str) and symbol in self._settings.allowed_symbols
        ]

        confidence = raw.get("confidence")
        if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
            return {
                "available": False,
                "complete": False,
                "reason": "confidence_invalid",
                "enrichment_only": True,
                "decision_eligibility_asserted": False,
            }

        if float(confidence) < self._settings.min_confidence:
            return {
                "available": False,
                "complete": False,
                "reason": "confidence_below_threshold",
                "enrichment_only": True,
                "decision_eligibility_asserted": False,
            }

        return {
            "available": True,
            "complete": True,
            "provider": self._settings.provider,
            "symbols": filtered_symbols,
            "topics": raw.get("topics", []),
            "sentiment": raw.get("sentiment", "NEUTRAL"),
            "relevance_confidence": float(confidence),
            "enrichment_only": True,
            "decision_eligibility_asserted": False,
        }
