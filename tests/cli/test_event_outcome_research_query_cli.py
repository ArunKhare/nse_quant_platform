"""Tests for bounded event outcome research query CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nse_quant.cli.event_outcome_research_query_cli import (
    EventOutcomeResearchQuerySettings,
    build_parser,
    query_event_outcome_research,
)


class FakeStore:
    def __init__(self, rows: list[tuple] | None = None) -> None:
        class FakeConnection:
            def __init__(self, result_rows: list[tuple]) -> None:
                self.rows = result_rows

            def execute(self, *_args, **_kwargs) -> FakeConnection:
                return self

            def fetchall(self) -> list[tuple]:
                return self.rows

        self.conn = FakeConnection(rows or [])


def test_query_valid_payload():
    settings = EventOutcomeResearchQuerySettings(enabled=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
    }
    store = FakeStore(
        rows=[
            (
                "persistence-1",
                "panel-1",
                "event-1",
                "NIFTY",
                60,
                json.dumps({"spot_return_pct": 1.0}),
                None,
            )
        ]
    )
    result = query_event_outcome_research(
        payload=payload,
        settings=settings,
        store=store,
    )
    assert result["status"] == "QUERIED"
    assert result["count"] == 1
    assert result["records"][0]["event_id"] == "event-1"


def test_query_disabled_rejects():
    settings = EventOutcomeResearchQuerySettings(enabled=False)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
    }
    result = query_event_outcome_research(
        payload=payload,
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_outcome_research_query_disabled"


def test_query_missing_fields_rejected():
    settings = EventOutcomeResearchQuerySettings(enabled=True)
    result = query_event_outcome_research(
        payload={},
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "event_id" in result["missing"]


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        EventOutcomeResearchQuerySettings(max_records=0)


def test_parser_requires_db_and_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["query"])


def test_main_rejects_missing_db(tmp_path: Path, capsys):
    from nse_quant.cli.event_outcome_research_query_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{}", encoding="utf-8")
    exit_code = main(
        [
            "query",
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
    from nse_quant.cli.event_outcome_research_query_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    exit_code = main(
        [
            "query",
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
    from nse_quant.cli.event_outcome_research_query_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "query",
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
