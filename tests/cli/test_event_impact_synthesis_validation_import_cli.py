"""Tests for bounded event impact synthesis validation import CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nse_quant.cli.event_impact_synthesis_validation_import_cli import (
    EventImpactSynthesisValidationImportSettings,
    build_parser,
    import_event_impact_validation,
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


def test_import_valid_payload():
    settings = EventImpactSynthesisValidationImportSettings(enabled=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "records": [
            {
                "validation_id": "validation-1",
                "synthesis_id": "synthesis-1",
                "event_id": "event-1",
                "instrument": "NIFTY",
                "decision_ts": "2026-01-01T10:00:00+00:00",
                "validation": {"useful": True},
            }
        ],
    }
    result = import_event_impact_validation(
        payload=payload,
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "IMPORTED"
    assert result["imported"] == 1


def test_import_disabled_rejects():
    settings = EventImpactSynthesisValidationImportSettings(enabled=False)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "records": [],
    }
    result = import_event_impact_validation(
        payload=payload,
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_impact_synthesis_validation_import_disabled"


def test_import_missing_fields_rejected():
    settings = EventImpactSynthesisValidationImportSettings(enabled=True)
    result = import_event_impact_validation(
        payload={},
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "event_id" in result["missing"]


def test_import_records_not_list_rejected():
    settings = EventImpactSynthesisValidationImportSettings(enabled=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "records": "not-a-list",
    }
    result = import_event_impact_validation(
        payload=payload,
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "records_must_be_list"


def test_import_too_many_records_rejected():
    settings = EventImpactSynthesisValidationImportSettings(enabled=True, max_records=1)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "records": [
            {
                "validation_id": "validation-1",
                "synthesis_id": "synthesis-1",
                "event_id": "event-1",
                "instrument": "NIFTY",
                "decision_ts": "2026-01-01T10:00:00+00:00",
                "validation": {},
            },
            {
                "validation_id": "validation-2",
                "synthesis_id": "synthesis-2",
                "event_id": "event-1",
                "instrument": "NIFTY",
                "decision_ts": "2026-01-01T10:00:00+00:00",
                "validation": {},
            },
        ],
    }
    result = import_event_impact_validation(
        payload=payload,
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "too_many_records"


def test_import_input_too_large_rejected():
    settings = EventImpactSynthesisValidationImportSettings(enabled=True, max_input_bytes=10)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "records": [],
    }
    result = import_event_impact_validation(
        payload=payload,
        settings=settings,
        store=FakeStore(),
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "input_too_large"


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        EventImpactSynthesisValidationImportSettings(max_records=0)


def test_parser_requires_db_and_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["import"])


def test_main_rejects_missing_db(tmp_path: Path, capsys):
    from nse_quant.cli.event_impact_synthesis_validation_import_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{}", encoding="utf-8")
    exit_code = main(
        [
            "import",
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
    from nse_quant.cli.event_impact_synthesis_validation_import_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    exit_code = main(
        [
            "import",
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
    from nse_quant.cli.event_impact_synthesis_validation_import_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "import",
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
