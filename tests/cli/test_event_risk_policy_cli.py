"""Tests for bounded event-risk policy CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nse_quant.cli.event_risk_policy_cli import (
    build_parser,
    run_evaluate,
)
from nse_quant.risk.event_risk_policy import EventRiskPolicySettings


def test_run_evaluate_blocks_new_entries():
    settings = EventRiskPolicySettings(enabled=True)
    payload = {
        "event_impact": {"block_new_entries": True},
        "reaction": {},
    }
    result = run_evaluate(payload=payload, settings=settings)
    assert result["status"] == "EVALUATED"
    assert result["action"] == "BLOCK_NEW_ENTRIES"
    assert result["size_multiplier"] == 0.0


def test_run_evaluate_reduces_size_on_high_volatility():
    settings = EventRiskPolicySettings(
        enabled=True,
        reduce_size_on_high_volatility=True,
        max_size_reduction_pct=50.0,
    )
    payload = {
        "event_impact": {"volatility_impact": "high"},
        "reaction": {},
    }
    result = run_evaluate(payload=payload, settings=settings)
    assert result["status"] == "EVALUATED"
    assert result["action"] == "REDUCE_SIZE"
    assert result["size_multiplier"] == 0.5


def test_run_evaluate_reviews_open_positions_on_iv_crush():
    settings = EventRiskPolicySettings(
        enabled=True,
        review_iv_crush_threshold=-0.02,
    )
    payload = {
        "event_impact": {},
        "reaction": {"atm_iv_change": -0.03},
    }
    result = run_evaluate(payload=payload, settings=settings)
    assert result["status"] == "EVALUATED"
    assert result["action"] == "REVIEW_OPEN_POSITIONS"
    assert result["size_multiplier"] == 1.0


def test_run_evaluate_observes_when_no_rule_triggered():
    settings = EventRiskPolicySettings(enabled=True)
    payload: dict[str, dict[str, object]] = {
        "event_impact": {},
        "reaction": {},
    }
    result = run_evaluate(payload=payload, settings=settings)
    assert result["status"] == "EVALUATED"
    assert result["action"] == "OBSERVE"
    assert result["size_multiplier"] == 1.0


def test_run_evaluate_rejects_disabled_policy():
    settings = EventRiskPolicySettings(enabled=False)
    payload = {
        "event_impact": {"block_new_entries": True},
        "reaction": {},
    }
    result = run_evaluate(payload=payload, settings=settings)
    assert result["status"] == "EVALUATED"
    assert result["action"] == "OBSERVE"
    assert result["size_multiplier"] == 1.0


def test_run_evaluate_rejects_invalid_event_impact():
    settings = EventRiskPolicySettings(enabled=True)
    payload = {
        "event_impact": "not-a-dict",
        "reaction": {},
    }
    result = run_evaluate(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "event_impact_must_be_object"


def test_run_evaluate_rejects_invalid_reaction():
    settings = EventRiskPolicySettings(enabled=True)
    payload = {
        "event_impact": {},
        "reaction": "not-a-dict",
    }
    result = run_evaluate(payload=payload, settings=settings)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "reaction_must_be_object"


def test_parser_requires_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["evaluate"])


def test_main_rejects_missing_input(tmp_path: Path, capsys):
    from nse_quant.cli.event_risk_policy_cli import main

    exit_code = main(
        [
            "evaluate",
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
    from nse_quant.cli.event_risk_policy_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "evaluate",
            "--input",
            str(input_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "invalid_input_file"
