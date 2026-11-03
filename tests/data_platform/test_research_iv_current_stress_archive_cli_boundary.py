"""Actual seven-file CLI/native/model/archive; inspected memory fixture helper unchanged.

Supplied for repository QA; not sandbox-executed or acquisition-native E2E.
"""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from iv_bundle_inspection_fixture_files import bind_fixture_sources, fixture_arguments
from test_research_iv_stress_archive_revalidation_boundary import archive_case as archive_case
from test_research_iv_stress_archive_revalidation_boundary import (
    archive_stress_case as archive_stress_case,
)
from test_research_iv_stress_archive_revalidation_boundary import artifact_case as artifact_case
from test_research_iv_stress_archive_revalidation_boundary import bundle_case as bundle_case
from test_research_iv_stress_archive_revalidation_boundary import (
    current_bundle_case as current_bundle_case,
)
from test_research_iv_stress_archive_revalidation_boundary import (
    current_stage_case as current_stage_case,
)
from test_research_iv_stress_archive_revalidation_boundary import (
    current_stress_case as current_stress_case,
)
from test_research_iv_stress_archive_revalidation_boundary import (
    revalidation_case as revalidation_case,
)
from test_research_iv_stress_archive_revalidation_boundary import scenario as scenario
from test_research_iv_stress_archive_revalidation_boundary import setup as setup
from test_research_iv_stress_archive_revalidation_boundary import stage_case as stage_case
from test_research_iv_stress_archive_revalidation_boundary import stress_case as stress_case
from test_research_iv_stress_archive_revalidation_boundary import writer as writer

from nse_quant.data_platform import native_research_iv_spot_stress as native
from nse_quant.data_platform import research_iv_current_stress_archive_cli as cli
from nse_quant.data_platform import research_iv_stress_archive_revalidation as service


def readonly_arguments(target, recorded, path, case):
    # Existing helper exports ACTUAL memory SQL; retains owners and closes real file owners.
    names = (*cli.PATH_NAMES[:6], "bundle-archive-db")
    _, paths = fixture_arguments(case, names)
    assert Path(path).is_file()
    paths = paths[:6] + [str(path)]
    target.close()
    args: list[str] = []
    for name, selected in zip(cli.PATH_NAMES, paths, strict=True):
        args.extend(("--" + name, selected))
    args.extend(
        (
            "--stress-record-id-pin",
            recorded.build_id,
            "--recording-fingerprint",
            recorded.evidence_fingerprint,
            "--execute",
        )
    )
    return args, paths


@pytest.fixture
def cli_case(current_stress_case, monkeypatch):
    _, target, recorded, path, case = current_stress_case
    args, paths = readonly_arguments(target, recorded, path, case)
    # Same actual seven-handle identity adapter, no rewrite/removal of source assertion.
    with bind_fixture_sources(cli, case[5], monkeypatch):
        yield args, paths, recorded, case


def test_actual_cli_positive_readonly_without_file_changes(cli_case, capsys):
    args, paths, recorded, _ = cli_case
    before = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "matched_current_research_iv_spot_stress_archive"
    assert all(result[k] is True for k in cli.OBSERVATION_FLAGS)
    assert all(result[k] is False for k in cli.DENIAL_FLAGS)
    assert result["stress_record_id"] == recorded.build_id
    assert result["expected_recording_fingerprint"] == recorded.evidence_fingerprint
    assert result["accepted_study_metadata"]["shocks_bps"] == [0]
    assert result["native_stress_fingerprint"] is not None
    assert result["evidence_fingerprint"] is not None
    assert not any(k in result for k in ("study", "fresh_before", "archive_before", "comparison"))
    assert {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths} == before


def test_wrong_reviewed_recording_fp_never_reprices(cli_case, monkeypatch, capsys):
    args = cli_case[0]
    args[args.index("--recording-fingerprint") + 1] = "0" * 64

    def forbidden(*args, **kwargs):
        raise AssertionError("Unreviewed recording reached pricing")

    monkeypatch.setattr(native, "build_native_research_iv_spot_stress", forbidden)
    assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["reason_codes"] == ["STRESS_NOT_EXACT_REVIEWED_RECORDING"]
    assert result["accepted_study_metadata"] is None and result["evidence_fingerprint"] is None


def test_changed_source_not_hidden_by_original_good_record(cli_case, capsys):
    args, _, _, case = cli_case
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["current_source_checked"] is True
    assert result["model_computation_rechecked"] is False
    assert result["exact_recording_reproduced"] is False
    assert result["archive_unchanged_observed"] is True
    assert result["accepted_study_metadata"] is None and result["native_stress_fingerprint"] is None


def test_recorded_review_never_upgraded(archive_stress_case, monkeypatch, capsys):
    execute, target, path, case = archive_stress_case
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    recorded = execute()
    state[option.source_assessment_revision_id] = option
    args, _ = readonly_arguments(target, recorded, path, case)

    def forbidden(*args, **kwargs):
        raise AssertionError("Archived review reached later-good pricing")

    monkeypatch.setattr(native, "build_native_research_iv_spot_stress", forbidden)
    with bind_fixture_sources(cli, case[5], monkeypatch):
        assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["reason_codes"] == ["RECORDED_STRESS_REVIEW_CANNOT_BE_PROMOTED"]
    assert result["archived_recording_verified"] is True
    assert result["current_source_checked"] is False
    assert result["accepted_study_metadata"] is None


def test_exception_after_actual_native_service_sanitized(cli_case, monkeypatch, capsys):
    real = service.revalidate_research_iv_spot_stress_archive

    def fail_after_actual(*args, **kwargs):
        value = real(*args, **kwargs)
        assert value.status == "matched_current_research_iv_spot_stress_archive"
        raise RuntimeError("PRIVATE_POST_NATIVE_PAYLOAD")

    monkeypatch.setattr(service, "revalidate_research_iv_spot_stress_archive", fail_after_actual)
    assert cli.main(cli_case[0]) == 1
    captured = capsys.readouterr()
    assert "PRIVATE_POST_NATIVE_PAYLOAD" not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "status": "FAILED",
        "reason_code": "IV_CURRENT_STRESS_INSPECTION_FAILED",
    }
