"""Tests for bounded news enrichment persistence."""

from __future__ import annotations

from types import SimpleNamespace

import duckdb

from nse_quant.research.news_enrichment import (
    NewsEnrichmentSettings,
    enrich_news_item,
)
from nse_quant.research.news_enrichment_store import NewsEnrichmentStore


def build_store():
    conn = duckdb.connect()
    conn.execute(
        """
        CREATE TABLE news_enrichment (
            enrichment_id VARCHAR PRIMARY KEY,
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


def build_store_wrapper(store):
    settings = NewsEnrichmentSettings(
        enabled=True,
        allowed_symbols=["NIFTY"],
    )
    return NewsEnrichmentStore(store=store, settings=settings)


def test_inserts_enrichment_once():
    store = build_store()
    wrapper = build_store_wrapper(store)
    item = {"headline": "RBI policy decision may affect NIFTY"}
    enrichment = enrich_news_item(
        item,
        NewsEnrichmentSettings(
            enabled=True,
            allowed_symbols=["NIFTY"],
        ),
    )
    first = wrapper.persist(item, enrichment)
    second = wrapper.persist(item, enrichment)
    assert first["status"] == "INSERTED"
    assert second["status"] == "DUPLICATE"
    count = store.conn.execute("SELECT count(*) FROM news_enrichment").fetchone()[0]
    assert count == 1


def test_disabled_store_rejects():
    store = build_store()
    wrapper = NewsEnrichmentStore(
        store=store,
        settings=NewsEnrichmentSettings(enabled=False),
    )
    result = wrapper.persist(
        {"headline": "test"},
        {"available": True},
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "news_enrichment_disabled"


def test_unavailable_enrichment_rejected():
    store = build_store()
    wrapper = build_store_wrapper(store)
    result = wrapper.persist(
        {"headline": "test"},
        {"available": False},
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "enrichment_unavailable"


def test_missing_headline_rejected():
    store = build_store()
    wrapper = build_store_wrapper(store)
    result = wrapper.persist(
        {},
        {"available": True},
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "headline_required"
