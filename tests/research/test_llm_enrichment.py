"""Tests for bounded LLM enrichment adapter."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from nse_quant.research.llm_enrichment import (
    LLMEnrichmentAdapter,
    LLMEnrichmentSettings,
)


def build_adapter(**overrides):
    defaults = {
        "enabled": True,
        "provider": "manual",
        "max_headline_length": 512,
        "min_confidence": 0.0,
        "allowed_symbols": ["NIFTY"],
    }
    defaults.update(overrides)
    settings = LLMEnrichmentSettings(**defaults)

    def enricher(_item: dict[str, Any]) -> dict[str, Any]:
        return {
            "symbols": ["NIFTY"],
            "topics": ["monetary_policy"],
            "sentiment": "NEUTRAL",
            "confidence": 0.9,
        }

    return LLMEnrichmentAdapter(settings=settings, enricher=enricher)


def test_enriches_valid_item():
    adapter = build_adapter()
    result = adapter.enrich({"headline": "RBI policy decision may affect NIFTY"})
    assert result["available"] is True
    assert result["complete"] is True
    assert result["symbols"] == ["NIFTY"]
    assert result["relevance_confidence"] == 0.9


def test_disabled_adapter_rejects():
    adapter = build_adapter(enabled=False)
    result = adapter.enrich({"headline": "test"})
    assert result["available"] is False
    assert result["reason"] == "llm_enrichment_disabled"


def test_missing_headline_rejected():
    adapter = build_adapter()
    result = adapter.enrich({})
    assert result["available"] is False
    assert result["reason"] == "headline_required"


def test_oversized_headline_rejected():
    adapter = build_adapter(max_headline_length=10)
    result = adapter.enrich({"headline": "x" * 11})
    assert result["available"] is False
    assert result["reason"] == "headline_too_long"


def test_missing_enricher_rejected():
    adapter = LLMEnrichmentAdapter(
        settings=LLMEnrichmentSettings(enabled=True, allowed_symbols=["NIFTY"]),
        enricher=None,
    )
    result = adapter.enrich({"headline": "test"})
    assert result["available"] is False
    assert result["reason"] == "enricher_not_configured"


def test_invalid_enricher_output_rejected():
    adapter = LLMEnrichmentAdapter(
        settings=LLMEnrichmentSettings(enabled=True, allowed_symbols=["NIFTY"]),
        enricher=lambda item: "not-a-dict",
    )
    result = adapter.enrich({"headline": "test"})
    assert result["available"] is False
    assert result["reason"] == "enricher_output_invalid"


def test_invalid_symbols_rejected():
    adapter = LLMEnrichmentAdapter(
        settings=LLMEnrichmentSettings(enabled=True, allowed_symbols=["NIFTY"]),
        enricher=lambda item: {"symbols": "NIFTY", "confidence": 0.9},
    )
    result = adapter.enrich({"headline": "test"})
    assert result["available"] is False
    assert result["reason"] == "symbols_must_be_list"


def test_invalid_confidence_rejected():
    adapter = LLMEnrichmentAdapter(
        settings=LLMEnrichmentSettings(enabled=True, allowed_symbols=["NIFTY"]),
        enricher=lambda item: {"symbols": [], "confidence": 1.5},
    )
    result = adapter.enrich({"headline": "test"})
    assert result["available"] is False
    assert result["reason"] == "confidence_invalid"


def test_confidence_below_threshold_rejected():
    adapter = build_adapter(min_confidence=0.95)
    result = adapter.enrich({"headline": "test"})
    assert result["available"] is False
    assert result["reason"] == "confidence_below_threshold"


def test_disallowed_symbol_filtered():
    adapter = build_adapter()

    def enricher(_item: dict[str, Any]) -> dict[str, Any]:
        return {
            "symbols": ["NIFTY", "BANKNIFTY"],
            "topics": [],
            "sentiment": "NEUTRAL",
            "confidence": 0.9,
        }

    adapter._enricher = enricher
    result = adapter.enrich({"headline": "test"})
    assert result["symbols"] == ["NIFTY"]


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        LLMEnrichmentSettings(max_headline_length=0)
    with pytest.raises(ValidationError):
        LLMEnrichmentSettings(allowed_symbols=[" "])
