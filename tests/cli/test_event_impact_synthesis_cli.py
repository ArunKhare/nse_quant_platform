"""Tests for bounded event impact synthesis CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nse_quant.cli.event_impact_synthesis_cli import (
    EventImpactSynthesisSettings,
    build_parser,
    synthesize_event_impact,
)


def test_synthesize_valid_payload():
    settings = EventImpactSynthesisSettings(enabled=True, block_new_entries=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "2026-01-01T10:00:00+00:00",
        "mapping": {
            "direction": "CONDITIONAL",
            "volatility_impact": "high",
            "liquidity_impact": "medium",
            "confidence": 0.85,
        },
        "surprise": "HAWKISH",
    }
    result = synthesize_event_impact(payload=payload, settings=settings)
    assert result["status"] == "SYNTHESIZED"
    assert result["evidence"]["recommended_action"] == "BLOCK_NEW_ENTRIES"
    assert result["evidence"]["confidence"] == 0.85


def test_synthesize_disabled_rejects():
    settings = EventImpactSynthesisSettings(enabled=False)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "2026-01-01T10:00:00+00:00",
        "mapping": {},
    }
    result = synthesize_event_impact(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_impact_synthesis_disabled"


def test_synthesize_missing_fields_rejected():
    settings = EventImpactSynthesisSettings(enabled=True)
    result = synthesize_event_impact(payload={}, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "event_id" in result["missing"]


def test_synthesize_invalid_timestamp_rejected():
    settings = EventImpactSynthesisSettings(enabled=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "not-a-timestamp",
        "mapping": {},
    }
    result = synthesize_event_impact(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "invalid_timestamp"


def test_synthesize_invalid_mapping_rejected():
    settings = EventImpactSynthesisSettings(enabled=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "2026-01-01T10:00:00+00:00",
        "mapping": "not-a-dict",
    }
    result = synthesize_event_impact(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "mapping_must_be_object"


def test_synthesize_oversized_payload_rejected():
    settings = EventImpactSynthesisSettings(enabled=True, max_payload_bytes=10)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "2026-01-01T10:00:00+00:00",
        "mapping": {},
    }
    result = synthesize_event_impact(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "payload_too_large"


def test_synthesize_invalid_confidence_null():
    settings = EventImpactSynthesisSettings(enabled=True)
    payload = {
        "event_id": "event-1",
        "instrument": "NIFTY",
        "decision_ts": "2026-01-01T10:00:00+00:00",
        "mapping": {"confidence": 1.5},
    }
    result = synthesize_event_impact(payload=payload, settings=settings)
    assert result["status"] == "SYNTHESIZED"
    assert result["evidence"]["confidence"] is None


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        EventImpactSynthesisSettings(max_payload_bytes=0)


def test_parser_requires_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["synthesize"])


def test_main_rejects_missing_input(tmp_path: Path, capsys):
    from nse_quant.cli.event_impact_synthesis_cli import main

    exit_code = main(
        [
            "synthesize",
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
    from nse_quant.cli.event_impact_synthesis_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "synthesize",
            "--input",
            str(input_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "invalid_input_file"
