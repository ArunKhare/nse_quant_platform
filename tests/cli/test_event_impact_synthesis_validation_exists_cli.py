"""Tests for bounded event impact synthesis validation exists CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nse_quant.cli.event_impact_synthesis_validation_exists_cli import (
    EventImpactSynthesisValidationExistsSettings,
    build_parser,
    exists_event_impact_validation,
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


def test_exists_valid_payload():
    settings = EventImpactSynthesisValidationExistsSettings(enabled=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
    }
    store = FakeStore(
        rows=[
            (
                "persistence-1",
                "validation-1",
                "synthesis-1",
                "event-1",
                "NIFTY",
                None,
                json.dumps({"useful": True}),
                None,
            )
        ]
    )
    result = exists_event_impact_validation(
        payload=payload,
        settings=settings,
        store=store,
    )
    assert result["status"] == "EXISTS"
    assert result["exists"] is True


def test_exists_disabled_rejects():
    settings = EventImpactSynthesisValidationExistsSettings(enabled=False)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
    }
    result = exists_event_impact_validation(
        payload=payload,
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_impact_synthesis_validation_exists_disabled"


def test_exists_missing_fields_rejected():
    settings = EventImpactSynthesisValidationExistsSettings(enabled=True)
    result = exists_event_impact_validation(
        payload={},
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "event_id" in result["missing"]


def test_exists_no_records_rejected():
    settings = EventImpactSynthesisValidationExistsSettings(enabled=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
    }
    result = exists_event_impact_validation(
        payload=payload,
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "EXISTS"
    assert result["exists"] is False


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        EventImpactSynthesisValidationExistsSettings(max_records=0)


def test_parser_requires_db_and_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["exists"])


def test_main_rejects_missing_db(tmp_path: Path, capsys):
    from nse_quant.cli.event_impact_synthesis_validation_exists_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{}", encoding="utf-8")
    exit_code = main(
        [
            "exists",
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
    from nse_quant.cli.event_impact_synthesis_validation_exists_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    exit_code = main(
        [
            "exists",
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
    from nse_quant.cli.event_impact_synthesis_validation_exists_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "exists",
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
