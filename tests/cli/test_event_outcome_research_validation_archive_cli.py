"""Tests for bounded event outcome research validation archive CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nse_quant.cli.event_outcome_research_validation_archive_cli import (
    EventOutcomeResearchValidationArchiveSettings,
    archive_event_outcome_research,
    build_parser,
)


class FakeStore:
    def __init__(self, rows: list[tuple] | None = None) -> None:
        self.rows = rows or []
        self.conn = type(
            "FakeConn",
            (),
            {
                "execute": staticmethod(lambda *args, **kwargs: None),
                "fetchall": staticmethod(lambda: self.rows),
            },
        )()


def test_archive_valid_payload(tmp_path: Path):
    settings = EventOutcomeResearchValidationArchiveSettings(enabled=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
    }
    store = FakeStore(
        rows=[
            (
                "persistence-1",
                "validation-1",
                "event-1",
                "NIFTY",
                None,
                json.dumps({"useful": True}),
                None,
            )
        ]
    )
    output_path = tmp_path / "archive.jsonl"
    result = archive_event_outcome_research(
        payload=payload,
        settings=settings,
        store=store,
        output_path=output_path,
    )
    assert result["status"] == "ARCHIVED"
    assert result["archived"] == 1
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").count("\n") == 1


def test_archive_disabled_rejects(tmp_path: Path):
    settings = EventOutcomeResearchValidationArchiveSettings(enabled=False)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
    }
    result = archive_event_outcome_research(
        payload=payload,
        settings=settings,
        store=FakeStore(),
        output_path=tmp_path / "archive.jsonl",
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_outcome_research_validation_archive_disabled"


def test_archive_missing_fields_rejected(tmp_path: Path):
    settings = EventOutcomeResearchValidationArchiveSettings(enabled=True)
    result = archive_event_outcome_research(
        payload={},
        settings=settings,
        store=FakeStore(),
        output_path=tmp_path / "archive.jsonl",
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "event_id" in result["missing"]


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        EventOutcomeResearchValidationArchiveSettings(max_records=0)


def test_parser_requires_db_input_output():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["archive"])


def test_main_rejects_missing_db(tmp_path: Path, capsys):
    from nse_quant.cli.event_outcome_research_validation_archive_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{}", encoding="utf-8")
    exit_code = main(
        [
            "archive",
            "--db",
            str(tmp_path / "missing.duckdb"),
            "--input",
            str(input_path),
            "--output",
            str(tmp_path / "archive.jsonl"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "database_not_found"


def test_main_rejects_missing_input(tmp_path: Path, capsys):
    from nse_quant.cli.event_outcome_research_validation_archive_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    exit_code = main(
        [
            "archive",
            "--db",
            str(db_path),
            "--input",
            str(tmp_path / "missing.json"),
            "--output",
            str(tmp_path / "archive.jsonl"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "input_file_not_found"


def test_main_rejects_invalid_json(tmp_path: Path, capsys):
    from nse_quant.cli.event_outcome_research_validation_archive_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "archive",
            "--db",
            str(db_path),
            "--input",
            str(input_path),
            "--output",
            str(tmp_path / "archive.jsonl"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "invalid_input_file"
