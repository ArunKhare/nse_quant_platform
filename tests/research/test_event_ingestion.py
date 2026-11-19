"""Tests for bounded event ingestion service."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import duckdb
import pytest
from pydantic import ValidationError

from nse_quant.research.event_ingestion import (
    EventIngestionService,
    EventIngestionSettings,
)

AT = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


def build_store():
    conn = duckdb.connect()
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
    return SimpleNamespace(conn=conn)


def build_service(store, **overrides):
    defaults = {
        "enabled": True,
        "allowed_sources": ["manual_review"],
        "max_payload_bytes": 65536,
    }
    defaults.update(overrides)
    return EventIngestionService(
        store=store,
        settings=EventIngestionSettings(**defaults),
    )


def valid_event():
    return {
        "event_id": "event-1",
        "source": "manual_review",
        "event_type": "RBI_POLICY",
        "title": "RBI policy",
        "description": "Scheduled policy decision",
        "symbol": "NIFTY",
        "event_ts": AT,
        "importance": "high",
        "affected_underlyings": ["NIFTY"],
    }


def test_disabled_service_rejects():
    service = build_service(build_store(), enabled=False)
    result = service.ingest(valid_event())
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_ingestion_disabled"


def test_missing_fields_are_rejected():
    service = build_service(build_store())
    event = valid_event()
    del event["event_id"]
    result = service.ingest(event)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "event_id" in result["missing"]


def test_disallowed_source_is_rejected():
    service = build_service(build_store(), allowed_sources=["other"])
    result = service.ingest(valid_event())
    assert result["status"] == "REJECTED"
    assert result["reason"] == "source_not_allowed"


def test_naive_timestamp_is_rejected():
    service = build_service(build_store())
    event = valid_event()
    event["event_ts"] = datetime(2026, 1, 1, 10, 0)
    result = service.ingest(event)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "aware_event_timestamp_required"


def test_oversized_payload_is_rejected():
    service = build_service(build_store(), max_payload_bytes=10)
    result = service.ingest(valid_event())
    assert result["status"] == "REJECTED"
    assert result["reason"] == "payload_too_large"


def test_invalid_affected_underlyings_rejected():
    service = build_service(build_store())
    event = valid_event()
    event["affected_underlyings"] = "NIFTY"
    result = service.ingest(event)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "affected_underlyings_must_be_list_or_object"


def test_valid_event_is_inserted_once():
    store = build_store()
    service = build_service(store)
    first = service.ingest(valid_event())
    second = service.ingest(valid_event())
    assert first["status"] == "INSERTED"
    assert second["status"] == "DUPLICATE"
    count = store.conn.execute("SELECT count(*) FROM market_events").fetchone()[0]
    assert count == 1


def test_invalid_settings_are_rejected():
    with pytest.raises(ValidationError):
        EventIngestionSettings(max_payload_bytes=0)
    with pytest.raises(ValidationError):
        EventIngestionSettings(allowed_sources=[" "])
