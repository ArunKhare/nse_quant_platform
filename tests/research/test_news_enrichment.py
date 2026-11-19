"""Tests for bounded offline news enrichment."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nse_quant.research.news_enrichment import (
    NewsEnrichmentSettings,
    enrich_news_item,
)


def settings(**overrides) -> NewsEnrichmentSettings:
    defaults = {
        "enabled": True,
        "allowed_symbols": ["NIFTY", "RELIANCE"],
        "max_headline_length": 512,
    }
    defaults.update(overrides)
    return NewsEnrichmentSettings(**defaults)


def test_disabled_enrichment_is_unavailable():
    result = enrich_news_item(
        {"headline": "RBI policy decision"},
        NewsEnrichmentSettings(enabled=False),
    )
    assert result["available"] is False
    assert result["reason"] == "news_enrichment_disabled"
    assert result["enrichment_only"] is True
    assert result["decision_eligibility_asserted"] is False


def test_missing_headline_is_unavailable():
    result = enrich_news_item({}, settings())
    assert result["available"] is False
    assert result["reason"] == "headline_required"


def test_oversized_headline_is_rejected():
    result = enrich_news_item(
        {"headline": "x" * 600},
        settings(max_headline_length=512),
    )
    assert result["available"] is False
    assert result["reason"] == "headline_too_long"


def test_symbol_and_topic_extraction():
    result = enrich_news_item(
        {"headline": "RBI policy decision may affect NIFTY"},
        settings(),
    )
    assert result["available"] is True
    assert result["symbols"] == ["NIFTY"]
    assert "monetary_policy" in result["topics"]
    assert result["relevance_confidence"] == pytest.approx(0.8)


def test_unknown_symbol_is_ignored():
    result = enrich_news_item(
        {"headline": "TCS results beat expectations"},
        settings(),
    )
    assert result["symbols"] == []
    assert "earnings" in result["topics"]
    assert result["sentiment"] == "POSITIVE"


def test_negative_sentiment_detected():
    result = enrich_news_item(
        {"headline": "Company reports loss and downgrade"},
        settings(),
    )
    assert result["sentiment"] == "NEGATIVE"


def test_neutral_when_no_keywords():
    result = enrich_news_item(
        {"headline": "Market update"},
        settings(),
    )
    assert result["sentiment"] == "NEUTRAL"
    assert result["topics"] == []
    assert result["relevance_confidence"] == 0.0


def test_invalid_settings_are_rejected():
    with pytest.raises(ValidationError):
        NewsEnrichmentSettings(max_headline_length=0)
    with pytest.raises(ValidationError):
        NewsEnrichmentSettings(min_relevance_confidence=2.0)
