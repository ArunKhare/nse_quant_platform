"""Tests for bounded event-risk CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nse_quant.cli.event_risk_cli import (
    build_parser,
    run_evaluate,
)


def test_run_evaluate_evaluates_valid_payload():
    plugin = type(
        "FakePlugin",
        (),
        {
            "evaluate": staticmethod(
                lambda **kwargs: {
                    "available": True,
                    "event_risk": {
                        "blocked_new_entries": True,
                        "matched_events": 1,
                        "evidence": [],
                    },
                }
            )
        },
    )()
    payload = {
        "run_id": "run-1",
        "instrument": "NIFTY",
        "decision_ts": "2026-01-01T10:00:00+00:00",
    }
    result = run_evaluate(payload=payload, plugin=plugin)
    assert result["status"] == "EVALUATED"
    assert result["event_risk"]["blocked_new_entries"] is True


def test_run_evaluate_rejects_missing_fields():
    plugin = type(
        "FakePlugin",
        (),
        {
            "evaluate": staticmethod(
                lambda **kwargs: {
                    "available": False,
                    "reason": "should_not_be_called",
                }
            )
        },
    )()
    result = run_evaluate(payload={}, plugin=plugin)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "run_id" in result["missing"]


def test_run_evaluate_rejects_invalid_timestamp():
    plugin = type(
        "FakePlugin",
        (),
        {
            "evaluate": staticmethod(
                lambda **kwargs: {
                    "available": False,
                    "reason": "should_not_be_called",
                }
            )
        },
    )()
    payload = {
        "run_id": "run-1",
        "instrument": "NIFTY",
        "decision_ts": "not-a-timestamp",
    }
    result = run_evaluate(payload=payload, plugin=plugin)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "invalid_timestamp"


def test_parser_requires_db_and_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["evaluate"])


def test_main_rejects_missing_db(tmp_path: Path, capsys):
    from nse_quant.cli.event_risk_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{}", encoding="utf-8")
    exit_code = main(
        [
            "evaluate",
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
    from nse_quant.cli.event_risk_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    exit_code = main(
        [
            "evaluate",
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
    from nse_quant.cli.event_risk_cli import main

    db_path = tmp_path / "test.duckdb"
    db_path.write_bytes(b"")
    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "evaluate",
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
