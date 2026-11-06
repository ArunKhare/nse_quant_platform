"""Tests for bounded event outcome research CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nse_quant.cli.event_outcome_research_cli import (
    EventOutcomeResearchSettings,
    build_event_outcome_panel,
    build_parser,
)


def test_build_valid_panel():
    settings = EventOutcomeResearchSettings(enabled=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "observation_window_minutes": 60,
        "baseline": {"spot": 100.0, "atm_iv": 0.14, "pcr": 1.0},
        "observed": {"spot": 101.0, "atm_iv": 0.12, "pcr": 1.1},
    }
    result = build_event_outcome_panel(payload=payload, settings=settings)
    assert result["status"] == "BUILT"
    assert result["panel"]["spot_return_pct"] == 1.0
    assert result["panel"]["atm_iv_change"] == -0.020000000000000018
    assert result["panel"]["pcr_change"] == 0.10000000000000009


def test_build_disabled_rejects():
    settings = EventOutcomeResearchSettings(enabled=False)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "observation_window_minutes": 60,
        "baseline": {},
        "observed": {},
    }
    result = build_event_outcome_panel(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_outcome_research_disabled"


def test_build_missing_fields_rejected():
    settings = EventOutcomeResearchSettings(enabled=True)
    result = build_event_outcome_panel(payload={}, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "event_id" in result["missing"]


def test_build_invalid_window_rejected():
    settings = EventOutcomeResearchSettings(enabled=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "observation_window_minutes": "not-a-number",
        "baseline": {},
        "observed": {},
    }
    result = build_event_outcome_panel(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "invalid_window"


def test_build_window_out_of_bounds_rejected():
    settings = EventOutcomeResearchSettings(enabled=True, observation_window_minutes=30)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "observation_window_minutes": 60,
        "baseline": {},
        "observed": {},
    }
    result = build_event_outcome_panel(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "window_out_of_bounds"


def test_build_oversized_payload_rejected():
    settings = EventOutcomeResearchSettings(enabled=True, max_payload_bytes=10)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "observation_window_minutes": 60,
        "baseline": {},
        "observed": {},
    }
    result = build_event_outcome_panel(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "payload_too_large"


def test_build_invalid_baseline_rejected():
    settings = EventOutcomeResearchSettings(enabled=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "observation_window_minutes": 60,
        "baseline": "not-a-dict",
        "observed": {},
    }
    result = build_event_outcome_panel(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "baseline_and_observed_must_be_objects"


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        EventOutcomeResearchSettings(observation_window_minutes=0)


def test_parser_requires_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["build"])


def test_main_rejects_missing_input(tmp_path: Path, capsys):
    from nse_quant.cli.event_outcome_research_cli import main

    exit_code = main(
        [
            "build",
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
    from nse_quant.cli.event_outcome_research_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "build",
            "--input",
            str(input_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "invalid_input_file"
