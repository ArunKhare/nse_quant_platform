"""Tests for bounded LLM enrichment-to-event linkage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import duckdb
import pytest
from pydantic import ValidationError

from nse_quant.research.llm_enrichment_links import (
    LLMEnrichmentEventLinker,
    LLMEnrichmentLinkSettings,
)

AT = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


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
    conn.execute(
        """
        CREATE TABLE market_events (
            event_id VARCHAR PRIMARY KEY,
            source VARCHAR,
            event_type VARCHAR,
            title VARCHAR,
            description TEXT,
            symbol VARCHAR,
            event_ts TIMESTAMPTZ,
            importance VARCHAR,
            consensus_value DOUBLE,
            actual_value DOUBLE,
            surprise_label VARCHAR,
            affected_underlyings JSON,
            raw_payload JSON,
            ingested_at TIMESTAMPTZ
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE llm_enrichment_event_links (
            link_id VARCHAR PRIMARY KEY,
            enrichment_id VARCHAR,
            event_id VARCHAR,
            instrument VARCHAR,
            linked_at TIMESTAMPTZ,
            payload JSON
        )
        """
    )
    conn.execute(
        "INSERT INTO llm_enrichment VALUES (?,?,?,?,?,?,?,?,?)",
        ["enrichment-1", "manual", "headline", "[]", "[]", "NEUTRAL", 0.0, "{}", AT],
    )
    conn.execute(
        "INSERT INTO market_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            "event-1",
            "manual_review",
            "RBI_POLICY",
            "title",
            "description",
            "NIFTY",
            AT,
            "high",
            None,
            None,
            None,
            "[]",
            "{}",
            AT,
        ],
    )
    return SimpleNamespace(conn=conn)


def build_linker(store, **overrides):
    defaults = {
        "enabled": True,
        "max_link_window_minutes": 60,
    }
    defaults.update(overrides)
    return LLMEnrichmentEventLinker(
        store=store,
        settings=LLMEnrichmentLinkSettings(**defaults),
    )


def test_links_llm_enrichment_to_event_once():
    store = build_store()
    linker = build_linker(store)
    first = linker.link(
        enrichment_id="enrichment-1",
        event_id="event-1",
        instrument="NIFTY",
        event_ts=AT,
        observed_at=AT + timedelta(minutes=15),
    )
    second = linker.link(
        enrichment_id="enrichment-1",
        event_id="event-1",
        instrument="NIFTY",
        event_ts=AT,
        observed_at=AT + timedelta(minutes=15),
    )
    assert first["status"] == "LINKED"
    assert second["status"] == "DUPLICATE"
    count = store.conn.execute("SELECT count(*) FROM llm_enrichment_event_links").fetchone()[0]
    assert count == 1


def test_disabled_linking_rejects():
    linker = build_linker(build_store(), enabled=False)
    result = linker.link(
        enrichment_id="enrichment-1",
        event_id="event-1",
        instrument="NIFTY",
        event_ts=AT,
        observed_at=AT,
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "llm_enrichment_linking_disabled"


def test_window_exceeded_rejects():
    linker = build_linker(build_store(), max_link_window_minutes=60)
    result = linker.link(
        enrichment_id="enrichment-1",
        event_id="event-1",
        instrument="NIFTY",
        event_ts=AT,
        observed_at=AT + timedelta(minutes=61),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "link_window_exceeded"


def test_missing_enrichment_rejects():
    linker = build_linker(build_store())
    result = linker.link(
        enrichment_id="missing",
        event_id="event-1",
        instrument="NIFTY",
        event_ts=AT,
        observed_at=AT,
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "enrichment_not_found"


def test_missing_event_rejects():
    linker = build_linker(build_store())
    result = linker.link(
        enrichment_id="enrichment-1",
        event_id="missing",
        instrument="NIFTY",
        event_ts=AT,
        observed_at=AT,
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_not_found"


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        LLMEnrichmentLinkSettings(max_link_window_minutes=0)
