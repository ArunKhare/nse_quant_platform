"""Tests for bounded event outcome research persistence CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nse_quant.cli.event_outcome_research_persistence_cli import (
    EventOutcomeResearchPersistenceSettings,
    build_parser,
    persist_event_outcome_panel,
)


class FakeStore:
    def __init__(self) -> None:
        self.conn = type(
            "FakeConn",
            (),
            {
                "execute": staticmethod(lambda *args, **kwargs: None),
            },
        )()


def test_persist_valid_panel():
    settings = EventOutcomeResearchPersistenceSettings(enabled=True)
    payload = {
        "panel_id": "panel-1",
        "event_id": "event-1",
        "instrument": "NIFTY",
        "observation_window_minutes": 60,
        "panel": {"spot_return_pct": 1.0},
    }
    result = persist_event_outcome_panel(
        payload=payload,
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "PERSISTED"
    assert result["persistence_id"]


def test_persist_disabled_rejects():
    settings = EventOutcomeResearchPersistenceSettings(enabled=False)
    payload = {
        "panel_id": "panel-1",
        "event_id": "event-1",
        "instrument": "NIFTY",
        "observation_window_minutes": 60,
        "panel": {},
    }
    result = persist_event_outcome_panel(
        payload=payload,
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_outcome_research_persistence_disabled"


def test_persist_missing_fields_rejected():
    settings = EventOutcomeResearchPersistenceSettings(enabled=True)
    result = persist_event_outcome_panel(
        payload={},
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "panel_id" in result["missing"]


def test_persist_oversized_payload_rejected():
    settings = EventOutcomeResearchPersistenceSettings(enabled=True, max_payload_bytes=10)
    payload = {
        "panel_id": "panel-1",
        "event_id": "event-1",
        "instrument": "NIFTY",
        "observation_window_minutes": 60,
        "panel": {},
    }
    result = persist_event_outcome_panel(
        payload=payload,
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "payload_too_large"


def test_persist_invalid_panel_rejected():
    settings = EventOutcomeResearchPersistenceSettings(enabled=True)
    payload = {
        "panel_id": "panel-1",
        "event_id": "event-1",
        "instrument": "NIFTY",
        "observation_window_minutes": 60,
        "panel": "not-a-dict",
    }
    result = persist_event_outcome_panel(
        payload=payload,
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "panel_must_be_object"


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        EventOutcomeResearchPersistenceSettings(max_payload_bytes=0)


def test_parser_requires_db_and_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["persist"])


def test_main_rejects_missing_db(tmp_path: Path, capsys):
    from nse_quant.cli.event_outcome_research_persistence_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{}", encoding="utf-8")
    exit_code = main(
        [
            "persist",
            "--db",
            str(tmp_path / "missing.duckdb"),
            "--input",
            str(input_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "database_not_found"


def test_main_rejects_missing_input(tmp_path: Path, capsys):
    from nse_quant.cli.event_outcome_research_persistence_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    exit_code = main(
        [
            "persist",
            "--db",
            str(db_path),
            "--input",
            str(tmp_path / "missing.json"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "input_file_not_found"


def test_main_rejects_invalid_json(tmp_path: Path, capsys):
    from nse_quant.cli.event_outcome_research_persistence_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "persist",
            "--db",
            str(db_path),
            "--input",
            str(input_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "invalid_input_file"
