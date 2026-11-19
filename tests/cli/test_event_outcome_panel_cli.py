"""Tests for bounded event outcome panel CLI."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from pydantic import ValidationError

from nse_quant.cli.event_outcome_panel_cli import (
    EventOutcomePanelSettings,
    build_event_outcome_panel,
    build_parser,
)

AT = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


def build_store():
    conn = duckdb.connect()
    conn.execute(
        """
        CREATE TABLE event_reactions (
            reaction_id VARCHAR PRIMARY KEY,
            event_id VARCHAR,
            instrument VARCHAR,
            captured_at TIMESTAMPTZ,
            payload JSON
        )
        """
    )
    conn.execute(
        "INSERT INTO event_reactions VALUES (?,?,?,?,?)",
        [
            "reaction-1",
            "event-1",
            "NIFTY",
            AT,
            json.dumps({"complete": True, "spot_return_pct": 1.0}),
        ],
    )
    return SimpleNamespace(conn=conn)


def test_build_panel_returns_rows():
    store = build_store()
    settings = EventOutcomePanelSettings(enabled=True, max_rows=1000)
    result = build_event_outcome_panel(
        store=store,
        settings=settings,
        event_id="event-1",
        instrument="NIFTY",
    )
    assert result["status"] == "BUILT"
    assert result["row_count"] == 1
    assert result["complete_count"] == 1
    assert result["rows"][0]["reaction_id"] == "reaction-1"


def test_build_panel_empty():
    store = build_store()
    settings = EventOutcomePanelSettings(enabled=True, max_rows=1000)
    result = build_event_outcome_panel(
        store=store,
        settings=settings,
        event_id="missing",
        instrument="NIFTY",
    )
    assert result["status"] == "BUILT"
    assert result["row_count"] == 0
    assert result["complete_count"] == 0


def test_build_panel_disabled():
    store = build_store()
    settings = EventOutcomePanelSettings(enabled=False, max_rows=1000)
    result = build_event_outcome_panel(
        store=store,
        settings=settings,
        event_id="event-1",
        instrument="NIFTY",
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_outcome_panel_disabled"


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        EventOutcomePanelSettings(max_rows=0)


def test_parser_requires_db_event_instrument():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["build"])


def test_main_rejects_missing_db(tmp_path: Path, capsys):
    from nse_quant.cli.event_outcome_panel_cli import main

    exit_code = main(
        [
            "build",
            "--db",
            str(tmp_path / "missing.duckdb"),
            "--event-id",
            "event-1",
            "--instrument",
            "NIFTY",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "database_not_found"
