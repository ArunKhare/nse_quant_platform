"""Tests for bounded LLM enrichment link CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nse_quant.cli.llm_enrichment_link_cli import (
    build_parser,
    run_link,
)


def test_run_link_links_valid_payload():
    linker = type(
        "FakeLinker",
        (),
        {
            "link": staticmethod(
                lambda **kwargs: {
                    "status": "LINKED",
                    "link_id": "link-1",
                    "decision_eligibility_asserted": False,
                }
            )
        },
    )()
    payload = {
        "enrichment_id": "enrichment-1",
        "event_id": "event-1",
        "instrument": "NIFTY",
        "event_ts": "2026-01-01T10:00:00+00:00",
        "observed_at": "2026-01-01T10:15:00+00:00",
    }
    result = run_link(payload=payload, linker=linker)
    assert result["status"] == "LINKED"
    assert result["link_id"] == "link-1"


def test_run_link_rejects_missing_fields():
    linker = type(
        "FakeLinker",
        (),
        {
            "link": staticmethod(
                lambda **kwargs: {
                    "status": "REJECTED",
                    "reason": "should_not_be_called",
                    "decision_eligibility_asserted": False,
                }
            )
        },
    )()
    result = run_link(payload={}, linker=linker)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "missing_required_fields"
    assert "enrichment_id" in result["missing"]


def test_run_link_rejects_invalid_timestamp():
    linker = type(
        "FakeLinker",
        (),
        {
            "link": staticmethod(
                lambda **kwargs: {
                    "status": "REJECTED",
                    "reason": "should_not_be_called",
                    "decision_eligibility_asserted": False,
                }
            )
        },
    )()
    payload = {
        "enrichment_id": "enrichment-1",
        "event_id": "event-1",
        "instrument": "NIFTY",
        "event_ts": "not-a-timestamp",
        "observed_at": "2026-01-01T10:15:00+00:00",
    }
    result = run_link(payload=payload, linker=linker)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "invalid_timestamp"


def test_parser_requires_input():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["link"])


def test_main_rejects_missing_file(tmp_path: Path, capsys):
    from nse_quant.cli.llm_enrichment_link_cli import main

    exit_code = main(
        [
            "link",
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
    from nse_quant.cli.llm_enrichment_link_cli import main

    input_path = tmp_path / "payload.json"
    input_path.write_text("{invalid", encoding="utf-8")
    exit_code = main(
        [
            "link",
            "--input",
            str(input_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "REJECTED"
    assert payload["reason"] == "invalid_input_file"
