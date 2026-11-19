"""Tests for bounded event impact synthesis validation truncate CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nse_quant.cli.event_impact_synthesis_validation_truncate_cli import (
    EventImpactSynthesisValidationTruncateSettings,
    build_parser,
    truncate_event_impact_validation,
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


def test_truncate_valid_payload():
    settings = EventImpactSynthesisValidationTruncateSettings(enabled=True)
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
    result = truncate_event_impact_validation(
        payload=payload,
        settings=settings,
        store=store,
    )
    assert result["status"] == "TRUNCATED"
    assert result["truncated"] == 1


def test_truncate_disabled_rejects():
    settings = EventImpactSynthesisValidationTruncateSettings(enabled=False)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
    }
    result = truncate_event_impact_validation(
        payload=payload,
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_impact_synthesis_validation_truncate_disabled"


def test_truncate_missing_fields_rejected():
    settings = EventImpactSynthesisValidationTruncateSettings(enabled=True)
    result = truncate_event_impact_validation(
        payload={},
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "event_id" in result["missing"]


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        EventImpactSynthesisValidationTruncateSettings(max_records=0)


def test_parser_requires_db_and_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["truncate"])


def test_main_rejects_missing_db(tmp_path: Path, capsys):
    from nse_quant.cli.event_impact_synthesis_validation_truncate_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{}", encoding="utf-8")
    exit_code = main(
        [
            "truncate",
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
    from nse_quant.cli.event_impact_synthesis_validation_truncate_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    exit_code = main(
        [
            "truncate",
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
    from nse_quant.cli.event_impact_synthesis_validation_truncate_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "truncate",
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
