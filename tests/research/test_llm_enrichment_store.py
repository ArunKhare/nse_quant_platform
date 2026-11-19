"""Tests for bounded LLM enrichment persistence."""

from __future__ import annotations

from types import SimpleNamespace

import duckdb
import pytest
from pydantic import ValidationError

from nse_quant.research.llm_enrichment import (
    LLMEnrichmentAdapter,
    LLMEnrichmentSettings,
)
from nse_quant.research.llm_enrichment_store import (
    LLMEnrichmentStore,
    LLMEnrichmentStoreSettings,
)


def build_store():
    conn = duckdb.connect()
    conn.execute(
        """
        CREATE TABLE llm_enrichment (
            enrichment_id VARCHAR PRIMARY KEY,
            provider VARCHAR,
            headline VARCHAR,
            symbols JSON,
            topics JSON,
            sentiment VARCHAR,
            relevance_confidence DOUBLE,
            enrichment JSON,
            ingested_at TIMESTAMPTZ
        )
        """
    )
    return SimpleNamespace(conn=conn)


def build_store_wrapper(store, **overrides):
    defaults = {
        "enabled": True,
        "max_payload_bytes": 65536,
    }
    defaults.update(overrides)
    return LLMEnrichmentStore(
        store=store,
        settings=LLMEnrichmentStoreSettings(**defaults),
    )


def build_adapter_settings(**overrides):
    defaults = {
        "enabled": True,
        "provider": "manual",
        "allowed_symbols": ["NIFTY"],
    }
    defaults.update(overrides)
    return LLMEnrichmentSettings(**defaults)


def enrich(item, settings):
    adapter = LLMEnrichmentAdapter(
        settings=settings,
        enricher=lambda x: {
            "symbols": ["NIFTY"],
            "topics": ["monetary_policy"],
            "sentiment": "NEUTRAL",
            "confidence": 0.9,
        },
    )
    return adapter.enrich(item)


def test_inserts_llm_enrichment_once():
    store = build_store()
    wrapper = build_store_wrapper(store)
    settings = build_adapter_settings()
    item = {"headline": "RBI policy decision may affect NIFTY"}
    enrichment = enrich(item, settings)
    first = wrapper.persist(item, enrichment, settings)
    second = wrapper.persist(item, enrichment, settings)
    assert first["status"] == "INSERTED"
    assert second["status"] == "DUPLICATE"
    count = store.conn.execute("SELECT count(*) FROM llm_enrichment").fetchone()[0]
    assert count == 1


def test_disabled_store_rejects():
    wrapper = build_store_wrapper(build_store(), enabled=False)
    result = wrapper.persist(
        {"headline": "test"},
        {"available": True, "complete": True},
        build_adapter_settings(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "llm_enrichment_store_disabled"


def test_unavailable_enrichment_rejected():
    wrapper = build_store_wrapper(build_store())
    result = wrapper.persist(
        {"headline": "test"},
        {"available": False, "complete": False},
        build_adapter_settings(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "enrichment_unavailable"


def test_missing_headline_rejected():
    wrapper = build_store_wrapper(build_store())
    result = wrapper.persist(
        {},
        {"available": True, "complete": True},
        build_adapter_settings(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "headline_required"


def test_oversized_payload_rejected():
    wrapper = build_store_wrapper(build_store(), max_payload_bytes=10)
    result = wrapper.persist(
        {"headline": "test"},
        {"available": True, "complete": True},
        build_adapter_settings(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "payload_too_large"


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        LLMEnrichmentStoreSettings(max_payload_bytes=0)
