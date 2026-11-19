"""Actual eight-DB read-only CLI/service boundary; lower source kernel substituted.

Supplied for local QA, NOT sandbox-executed and NOT full native acquisition E2E.
"""

import hashlib
import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from iv_bundle_inspection_fixture_files import fixture_arguments
from test_gold_quote_reader import setup as setup
from test_native_research_iv_artifact_boundary import artifact_case as artifact_case
from test_native_research_iv_bundle_boundary import bundle_case as bundle_case
from test_native_research_option_boundary import scenario as scenario
from test_research_iv_bundle_revalidation_boundary import (
    current_bundle_case as current_bundle_case,
)
from test_research_iv_bundle_store_boundary import writer as writer
from test_research_iv_current_stage_boundary import (
    current_stage_case as current_stage_case,
)
from test_research_iv_current_stage_boundary import pending
from test_research_iv_first_stage_boundary import stage_case as stage_case
from test_research_iv_revalidation_boundary import revalidation_case as revalidation_case
from test_research_iv_store_boundary import archive_case as archive_case

from nse_quant.data_platform import research_iv_current_stage_cli as cli
from nse_quant.data_platform import research_iv_stage_revalidation as service


@pytest.fixture(autouse=True)
def bind_actual_readonly_source_roles(current_stage_case, monkeypatch):
    # Reuse existing memory-source snapshot helper unmodified. Its original lower
    # source substitute asserts exact handle identity against THIS mutable list.
    sources = current_stage_case[5][5]
    real_open = cli._open_inputs

    @contextmanager
    def bind(paths, root):
        with real_open(paths, root) as handles:
            original = sources[:]
            assert len(original) == 4 and len(handles) == 8
            sources[:] = handles[:4]
            try:
                yield handles
            finally:
                sources[:] = original

    monkeypatch.setattr(cli, "_open_inputs", bind)
    yield


def readonly_arguments(case):
    _, staging, receipt, reviewed, root, bundle_case = case
    current = staging.execute("SELECT current_database()").fetchone()
    assert current is not None
    selected = [
        row[2] for row in staging.execute("PRAGMA database_list").fetchall() if row[1] == current[0]
    ]
    assert len(selected) == 1 and selected[0]
    # Only the first seven roles use the inspected memory-source export helper.
    # Native results/Gold rows are not fabricated; existing SQL contents are copied.
    _, paths = fixture_arguments(bundle_case, cli.PATH_NAMES[:7])
    paths.append(str(selected[0]))
    staging.close()
    args: list[str] = []
    for name, path in zip(cli.PATH_NAMES, paths, strict=True):
        args.extend(("--" + name, path))
    args.extend(
        (
            "--artifact-root",
            str(root),
            "--stage-build-id-pin",
            receipt["build_id"],
            "--stage-fingerprint",
            reviewed.evidence_fingerprint,
            "--execute",
        )
    )
    return args, paths, root


def test_actual_current_stage_cli_matches_without_database_or_artifact_changes(
    current_stage_case,
    capsys,
):
    args, paths, root = readonly_arguments(current_stage_case)
    all_files = [Path(path) for path in paths] + list(root.iterdir())
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in all_files}
    assert cli.main(args) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "matched_current_research_iv_stage"
    assert all(value[key] is True for key in cli.OBSERVATION_FLAGS)
    assert all(value[key] is False for key in cli.DENIAL_FLAGS)
    assert "stage_before" not in value and "fresh_before" not in value
    after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in all_files}
    assert before == after


def test_actual_wrong_stage_review_returns_review_not_latest_lookup(current_stage_case, capsys):
    args, _, _ = readonly_arguments(current_stage_case)
    args[args.index("--stage-fingerprint") + 1] = "0" * 64
    assert cli.main(args) == 2
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "review_required"
    assert value["current_source_checked"] is False and value["bundle_id"] is None


def test_actual_changed_source_cli_returns_review_without_old_good(current_stage_case, capsys):
    state, option = current_stage_case[5][-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    args, _, _ = readonly_arguments(current_stage_case)
    assert cli.main(args) == 2
    value = json.loads(capsys.readouterr().out)
    assert value["current_source_checked"] is True
    assert value["recorded_native_digests_matched"] is False
    assert value["bundle_id"] is None and value["evidence_fingerprint"] is None


def test_actual_pending_stage_obligation_cli_blocks(current_stage_case, capsys):
    pending(current_stage_case[1])
    args, _, _ = readonly_arguments(current_stage_case)
    assert cli.main(args) == 2
    value = json.loads(capsys.readouterr().out)
    assert value["reason_codes"] == ["IV_STAGE_ORIGINAL_RECORDING_NOT_COMPLETE_BEFORE"]
    assert value["current_source_checked"] is False


def test_service_error_is_sanitized_and_cannot_report_success(
    current_stage_case,
    monkeypatch,
    capsys,
):
    args, _, _ = readonly_arguments(current_stage_case)

    def fail(*args, **kwargs):
        raise RuntimeError("SYNTHETIC_SECRET_NATIVE_FAILURE")

    monkeypatch.setattr(service, "revalidate_research_iv_first_stage", fail)
    assert cli.main(args) == 1
    captured = capsys.readouterr()
    assert "SYNTHETIC_SECRET" not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "status": "FAILED",
        "reason_code": "IV_CURRENT_STAGE_INSPECTION_FAILED",
    }
