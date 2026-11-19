"""Actual CLI/read-only service integration, lower source kernel substituted; not E2E.

Supplied for local repository execution, not run in the delivery sandbox.
"""

import hashlib
import json
from dataclasses import replace

import pytest
from iv_bundle_inspection_fixture_files import bind_fixture_sources, fixture_arguments
from test_gold_quote_reader import setup as setup
from test_native_research_iv_bundle_boundary import bundle_case as bundle_case
from test_native_research_option_boundary import scenario as scenario
from test_research_iv_bundle_revalidation_boundary import (
    current_bundle_case as current_bundle_case,
)
from test_research_iv_bundle_revalidation_boundary import pending
from test_research_iv_bundle_store_boundary import writer as writer
from test_research_iv_revalidation_boundary import revalidation_case as revalidation_case
from test_research_iv_store_boundary import archive_case as archive_case

from nse_quant.data_platform import research_iv_bundle_inspect_cli as cli
from nse_quant.data_platform import research_iv_bundle_revalidation as service


def readonly_arguments(case):
    return fixture_arguments(case, cli.PATH_NAMES)


def test_actual_readonly_inspection_matches_and_changes_no_database(current_bundle_case, capsys):
    from pathlib import Path

    args, paths = readonly_arguments(current_bundle_case)
    before = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths}
    assert cli.main(args) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "matched_current_research_iv_bundle"
    assert value["exact_recording_reproduced"] is True
    assert value["all_members_revalidated"] is True
    assert value["publication_asserted"] is False
    assert value["decision_eligibility_asserted"] is False
    assert "archive_before" not in value and "fresh_before" not in value
    after = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths}
    assert before == after


def test_actual_wrong_review_fingerprint_returns_review(current_bundle_case, capsys):
    args, _ = readonly_arguments(current_bundle_case)
    args[args.index("--archive-fingerprint") + 1] = "0" * 64
    assert cli.main(args) == 2
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "review_required" and value["current_source_checked"] is False
    assert value["bundle_id"] is None


def test_actual_changed_source_returns_review_not_old_good(current_bundle_case, capsys):
    current, option = current_bundle_case[-2:]
    current[option.source_assessment_revision_id] = replace(option, status="blocked")
    args, _ = readonly_arguments(current_bundle_case)
    assert cli.main(args) == 2
    value = json.loads(capsys.readouterr().out)
    assert value["current_source_checked"] is True
    assert value["exact_recording_reproduced"] is False
    assert value["bundle_id"] is None


def test_actual_pending_origin_blocks_readonly_inspection(current_bundle_case, capsys):
    pending(current_bundle_case[0], current_bundle_case[3])
    args, _ = readonly_arguments(current_bundle_case)
    assert cli.main(args) == 2
    value = json.loads(capsys.readouterr().out)
    assert value["reason_codes"] == ["IV_BUNDLE_ARCHIVE_OR_AUDIT_NOT_COMPLETE_BEFORE"]
    assert value["current_source_checked"] is False


def test_service_exception_diagnostic_is_sanitized(current_bundle_case, monkeypatch, capsys):
    args, _ = readonly_arguments(current_bundle_case)

    def fail(*args, **kwargs):
        raise RuntimeError("SYNTHETIC_SECRET_EXCEPTION_PAYLOAD")

    monkeypatch.setattr(service, "revalidate_research_iv_bundle", fail)
    assert cli.main(args) == 1
    captured = capsys.readouterr()
    assert "SYNTHETIC_SECRET" not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "status": "FAILED",
        "reason_code": "IV_BUNDLE_INSPECTION_FAILED",
    }


@pytest.fixture(autouse=True)
def bind_inspection_source_roles(current_bundle_case, monkeypatch):
    sources = current_bundle_case[5]
    with bind_fixture_sources(cli, sources, monkeypatch):
        yield
