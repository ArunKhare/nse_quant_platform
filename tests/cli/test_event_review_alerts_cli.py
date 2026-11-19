"""Tests for bounded event review alerts CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nse_quant.cli.event_review_alerts_cli import (
    build_parser,
    run_evaluate,
)


def test_run_evaluate_emits_alert():
    manager = type(
        "FakeManager",
        (),
        {
            "evaluate": staticmethod(
                lambda **kwargs: {
                    "reason": ["iv_crush_after_event"],
                    "open_position_count": 1,
                    "decision": {},
                }
            )
        },
    )()
    payload = {
        "run_id": "run-1",
        "decision": {
            "action": "REVIEW_OPEN_POSITIONS",
            "size_multiplier": 1.0,
            "reasons": ["iv_crush_after_event"],
        },
        "open_positions": [{}],
    }
    result = run_evaluate(payload=payload, manager=manager)
    assert result["status"] == "EVALUATED"
    assert result["alert"]["open_position_count"] == 1


def test_run_evaluate_no_alert_when_no_positions():
    manager = type(
        "FakeManager",
        (),
        {"evaluate": staticmethod(lambda **kwargs: None)},
    )()
    payload = {
        "run_id": "run-1",
        "decision": {
            "action": "REVIEW_OPEN_POSITIONS",
            "size_multiplier": 1.0,
            "reasons": ["iv_crush_after_event"],
        },
        "open_positions": [],
    }
    result = run_evaluate(payload=payload, manager=manager)
    assert result["status"] == "NO_ALERT"
    assert result["alert"] is None


def test_run_evaluate_rejects_missing_fields():
    manager = type(
        "FakeManager",
        (),
        {
            "evaluate": staticmethod(
                lambda **kwargs: {
                    "status": "REJECTED",
                    "reason": "should_not_be_called",
                }
            )
        },
    )()
    result = run_evaluate(payload={}, manager=manager)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "run_id" in result["missing"]


def test_run_evaluate_rejects_invalid_decision():
    manager = type(
        "FakeManager",
        (),
        {
            "evaluate": staticmethod(
                lambda **kwargs: {
                    "status": "REJECTED",
                    "reason": "should_not_be_called",
                }
            )
        },
    )()
    payload = {
        "run_id": "run-1",
        "decision": "not-a-dict",
        "open_positions": [],
    }
    result = run_evaluate(payload=payload, manager=manager)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "decision_must_be_object"


def test_run_evaluate_rejects_invalid_open_positions():
    manager = type(
        "FakeManager",
        (),
        {
            "evaluate": staticmethod(
                lambda **kwargs: {
                    "status": "REJECTED",
                    "reason": "should_not_be_called",
                }
            )
        },
    )()
    payload = {
        "run_id": "run-1",
        "decision": {
            "action": "REVIEW_OPEN_POSITIONS",
            "size_multiplier": 1.0,
            "reasons": [],
        },
        "open_positions": "not-a-list",
    }
    result = run_evaluate(payload=payload, manager=manager)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "open_positions_must_be_list"


def test_parser_requires_db_and_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["evaluate"])


def test_main_rejects_missing_db(tmp_path: Path, capsys):
    from nse_quant.cli.event_review_alerts_cli import main

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
    from nse_quant.cli.event_review_alerts_cli import main

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
    from nse_quant.cli.event_review_alerts_cli import main

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
