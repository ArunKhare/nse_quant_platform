"""Tests for bounded event reaction capture CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nse_quant.cli.event_reaction_capture_cli import (
    build_parser,
    run_capture,
)


def test_run_capture_captures_valid_payload():
    recorder = type(
        "FakeRecorder",
        (),
        {
            "capture": staticmethod(
                lambda **kwargs: {
                    "reaction_id": "reaction-1",
                    "complete": True,
                }
            )
        },
    )()
    payload = {
        "event": {"event_id": "event-1"},
        "instrument": "NIFTY",
        "observation_window_minutes": 60,
        "baseline": {"spot": 100.0},
        "observed": {"spot": 101.0},
    }
    result = run_capture(payload=payload, recorder=recorder)
    assert result["status"] == "CAPTURED"
    assert result["reaction"]["reaction_id"] == "reaction-1"


def test_run_capture_rejects_missing_fields():
    recorder = type(
        "FakeRecorder",
        (),
        {
            "capture": staticmethod(
                lambda **kwargs: {
                    "status": "REJECTED",
                    "reason": "should_not_be_called",
                }
            )
        },
    )()
    result = run_capture(payload={}, recorder=recorder)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "event" in result["missing"]


def test_run_capture_rejects_signature_mismatch():
    recorder = type(
        "FakeRecorder",
        (),
        {"capture": staticmethod(lambda event_id: None)},
    )()
    payload = {
        "event": {"event_id": "event-1"},
        "instrument": "NIFTY",
        "observation_window_minutes": 60,
        "baseline": {},
        "observed": {},
    }
    result = run_capture(payload=payload, recorder=recorder)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "recorder_signature_mismatch"


def test_parser_requires_db_and_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["capture"])


def test_main_rejects_missing_db(tmp_path: Path, capsys):
    from nse_quant.cli.event_reaction_capture_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{}", encoding="utf-8")
    exit_code = main(
        [
            "capture",
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
    from nse_quant.cli.event_reaction_capture_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    exit_code = main(
        [
            "capture",
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
    from nse_quant.cli.event_reaction_capture_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "capture",
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
