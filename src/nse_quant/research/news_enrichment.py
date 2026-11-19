"""Bounded, offline news enrichment.

Produces enrichment-only metadata for reviewed news items. This module never
asserts event truth, never grants decision eligibility, and never enables live
trading.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


class NewsEnrichmentSettings(BaseModel):
    enabled: bool = False
    allowed_symbols: list[str] = Field(default_factory=list)
    max_headline_length: int = Field(default=512, ge=1)
    min_relevance_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    topic_keywords: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "monetary_policy": ["rbi", "repo", "rate", "policy"],
            "earnings": ["results", "earnings", "profit", "revenue"],
            "macro": ["inflation", "gdp", "budget", "federal"],
        }
    )

    sentiment_keywords: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "positive": ["beat", "growth", "upgrade", "profit"],
            "negative": ["miss", "loss", "downgrade", "decline"],
        }
    )


def enrich_news_item(
    item: dict[str, Any],
    settings: NewsEnrichmentSettings,
) -> dict[str, Any]:
    if not settings.enabled:
        return {
            "available": False,
            "complete": False,
            "reason": "news_enrichment_disabled",
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

    if len(headline) > settings.max_headline_length:
        return {
            "available": False,
            "complete": False,
            "reason": "headline_too_long",
            "enrichment_only": True,
            "decision_eligibility_asserted": False,
        }

    text = headline.lower()
    symbols = [
        symbol
        for symbol in settings.allowed_symbols
        if re.search(rf"\b{re.escape(symbol)}\b", headline, flags=re.IGNORECASE)
    ]

    topics = [
        topic
        for topic, keywords in settings.topic_keywords.items()
        if any(keyword in text for keyword in keywords)
    ]

    sentiment = "NEUTRAL"
    if any(keyword in text for keyword in settings.sentiment_keywords["positive"]):
        sentiment = "POSITIVE"
    elif any(keyword in text for keyword in settings.sentiment_keywords["negative"]):
        sentiment = "NEGATIVE"

    relevance = 0.0
    if symbols:
        relevance += 0.5
    if topics:
        relevance += 0.3
    if sentiment != "NEUTRAL":
        relevance += 0.2
    relevance = min(relevance, 1.0)

    return {
        "available": True,
        "complete": True,
        "symbols": symbols,
        "topics": topics,
        "sentiment": sentiment,
        "relevance_confidence": relevance,
        "enrichment_only": True,
        "decision_eligibility_asserted": False,
    }
