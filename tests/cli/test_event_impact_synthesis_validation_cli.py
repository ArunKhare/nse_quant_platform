"""Tests for bounded event impact synthesis validation CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nse_quant.cli.event_impact_synthesis_validation_cli import (
    EventImpactSynthesisValidationSettings,
    build_parser,
    validate_event_impact_synthesis,
)


def test_validate_valid_payload():
    settings = EventImpactSynthesisValidationSettings(enabled=True)
    payload = {
        "synthesis_id": "synthesis-1",
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "2026-01-01T10:00:00+00:00",
        "evidence": {"volatility_impact": "high"},
        "outcome": {
            "spot_return_pct": 1.5,
            "atm_iv_change": -0.02,
            "expected_move_change_points": -10.0,
        },
    }
    result = validate_event_impact_synthesis(payload=payload, settings=settings)
    assert result["status"] == "VALIDATED"
    assert result["validation"]["useful"] is True
    assert result["validation"]["iv_crush"] is True


def test_validate_disabled_rejects():
    settings = EventImpactSynthesisValidationSettings(enabled=False)
    payload = {
        "synthesis_id": "synthesis-1",
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "2026-01-01T10:00:00+00:00",
        "evidence": {},
        "outcome": {},
    }
    result = validate_event_impact_synthesis(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_impact_synthesis_validation_disabled"


def test_validate_missing_fields_rejected():
    settings = EventImpactSynthesisValidationSettings(enabled=True)
    result = validate_event_impact_synthesis(payload={}, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "synthesis_id" in result["missing"]


def test_validate_oversized_payload_rejected():
    settings = EventImpactSynthesisValidationSettings(enabled=True, max_payload_bytes=10)
    payload = {
        "synthesis_id": "synthesis-1",
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "2026-01-01T10:00:00+00:00",
        "evidence": {},
        "outcome": {},
    }
    result = validate_event_impact_synthesis(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "payload_too_large"


def test_validate_invalid_evidence_rejected():
    settings = EventImpactSynthesisValidationSettings(enabled=True)
    payload = {
        "synthesis_id": "synthesis-1",
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "2026-01-01T10:00:00+00:00",
        "evidence": "not-a-dict",
        "outcome": {},
    }
    result = validate_event_impact_synthesis(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "evidence_and_outcome_must_be_objects"


def test_validate_invalid_timestamp_rejected():
    settings = EventImpactSynthesisValidationSettings(enabled=True)
    payload = {
        "synthesis_id": "synthesis-1",
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "not-a-timestamp",
        "evidence": {},
        "outcome": {},
    }
    result = validate_event_impact_synthesis(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "invalid_timestamp"


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        EventImpactSynthesisValidationSettings(max_payload_bytes=0)


def test_parser_requires_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["validate"])


def test_main_rejects_missing_input(tmp_path: Path, capsys):
    from nse_quant.cli.event_impact_synthesis_validation_cli import main

    exit_code = main(
        [
            "validate",
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
    from nse_quant.cli.event_impact_synthesis_validation_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "validate",
            "--input",
            str(input_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "invalid_input_file"
