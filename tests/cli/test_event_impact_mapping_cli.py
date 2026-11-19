"""Tests for bounded event impact mapping CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nse_quant.cli.event_impact_mapping_cli import (
    build_parser,
    run_map,
)


def test_run_map_maps_valid_payload():
    mapper = type(
        "FakeMapper",
        (),
        {
            "map": staticmethod(
                lambda **kwargs: {
                    "event_id": "event-1",
                    "instrument": "NIFTY",
                    "direction": "CONDITIONAL",
                }
            )
        },
    )()
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "2026-01-01T10:00:00+00:00",
    }
    result = run_map(payload=payload, mapper=mapper)
    assert result["status"] == "MAPPED"
    assert result["mapping"]["event_id"] == "event-1"


def test_run_map_rejects_missing_fields():
    mapper = type(
        "FakeMapper",
        (),
        {
            "map": staticmethod(
                lambda **kwargs: {
                    "status": "REJECTED",
                    "reason": "should_not_be_called",
                }
            )
        },
    )()
    result = run_map(payload={}, mapper=mapper)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "event_id" in result["missing"]


def test_run_map_rejects_invalid_timestamp():
    mapper = type(
        "FakeMapper",
        (),
        {
            "map": staticmethod(
                lambda **kwargs: {
                    "status": "REJECTED",
                    "reason": "should_not_be_called",
                }
            )
        },
    )()
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "not-a-timestamp",
    }
    result = run_map(payload=payload, mapper=mapper)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "invalid_timestamp"


def test_run_map_rejects_signature_mismatch():
    mapper = type(
        "FakeMapper",
        (),
        {"map": staticmethod(lambda event_id: None)},
    )()
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "2026-01-01T10:00:00+00:00",
    }
    result = run_map(payload=payload, mapper=mapper)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "mapper_signature_mismatch"


def test_parser_requires_db_and_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["map"])


def test_main_rejects_missing_db(tmp_path: Path, capsys):
    from nse_quant.cli.event_impact_mapping_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{}", encoding="utf-8")
    exit_code = main(
        [
            "map",
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
    from nse_quant.cli.event_impact_mapping_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    exit_code = main(
        [
            "map",
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
    from nse_quant.cli.event_impact_mapping_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "map",
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
