"""Tests for bounded event impact synthesis validation export CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nse_quant.cli.event_impact_synthesis_validation_export_cli import (
    EventImpactSynthesisValidationExportSettings,
    build_parser,
    export_event_impact_validation,
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


def test_export_valid_payload(tmp_path: Path):
    settings = EventImpactSynthesisValidationExportSettings(enabled=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
    }
    output_path = tmp_path / "export.json"
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
    result = export_event_impact_validation(
        payload=payload,
        settings=settings,
        store=store,
        output_path=output_path,
    )
    assert result["status"] == "EXPORTED"
    assert result["count"] == 1
    assert output_path.exists()


def test_export_disabled_rejects(tmp_path: Path):
    settings = EventImpactSynthesisValidationExportSettings(enabled=False)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
    }
    output_path = tmp_path / "export.json"
    result = export_event_impact_validation(
        payload=payload,
        settings=settings,
        store=FakeStore(),
        output_path=output_path,
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_impact_synthesis_validation_export_disabled"


def test_export_missing_fields_rejected(tmp_path: Path):
    settings = EventImpactSynthesisValidationExportSettings(enabled=True)
    output_path = tmp_path / "export.json"
    result = export_event_impact_validation(
        payload={},
        settings=settings,
        store=FakeStore(),
        output_path=output_path,
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "event_id" in result["missing"]


def test_export_oversized_output_rejected(tmp_path: Path):
    settings = EventImpactSynthesisValidationExportSettings(enabled=True, max_output_bytes=10)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
    }
    output_path = tmp_path / "export.json"
    result = export_event_impact_validation(
        payload=payload,
        settings=settings,
        store=FakeStore(),
        output_path=output_path,
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "output_too_large"


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        EventImpactSynthesisValidationExportSettings(max_records=0)


def test_parser_requires_db_input_output():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["export"])


def test_main_rejects_missing_db(tmp_path: Path, capsys):
    from nse_quant.cli.event_impact_synthesis_validation_export_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{}", encoding="utf-8")
    output_path = tmp_path / "export.json"
    exit_code = main(
        [
            "export",
            "--db",
            str(tmp_path / "missing.duckdb"),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "database_not_found"


def test_main_rejects_missing_input(tmp_path: Path, capsys):
    from nse_quant.cli.event_impact_synthesis_validation_export_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    output_path = tmp_path / "export.json"
    exit_code = main(
        [
            "export",
            "--db",
            str(db_path),
            "--input",
            str(tmp_path / "missing.json"),
            "--output",
            str(output_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "input_file_not_found"


def test_main_rejects_invalid_json(tmp_path: Path, capsys):
    from nse_quant.cli.event_impact_synthesis_validation_export_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    output_path = tmp_path / "export.json"
    exit_code = main(
        [
            "export",
            "--db",
            str(db_path),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "invalid_input_file"
