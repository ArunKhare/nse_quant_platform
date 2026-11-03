"""Actual CLI/native/kernel/archive with real memory snapshots; lower source substitute unchanged.

Supplied for repository QA; not sandbox-executed and not acquisition-native E2E.
"""

import hashlib
import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from iv_bundle_inspection_fixture_files import fixture_arguments
from test_native_research_iv_spot_stress_boundary import archive_case as archive_case
from test_native_research_iv_spot_stress_boundary import artifact_case as artifact_case
from test_native_research_iv_spot_stress_boundary import bundle_case as bundle_case
from test_native_research_iv_spot_stress_boundary import current_bundle_case as current_bundle_case
from test_native_research_iv_spot_stress_boundary import current_stage_case as current_stage_case
from test_native_research_iv_spot_stress_boundary import revalidation_case as revalidation_case
from test_native_research_iv_spot_stress_boundary import scenario as scenario
from test_native_research_iv_spot_stress_boundary import setup as setup
from test_native_research_iv_spot_stress_boundary import stage_case as stage_case
from test_native_research_iv_spot_stress_boundary import stress_case as stress_case
from test_native_research_iv_spot_stress_boundary import writer as writer

from nse_quant.data_platform import native_research_iv_spot_stress as service
from nse_quant.data_platform import research_iv_spot_stress_cli as cli


@pytest.fixture(autouse=True)
def bind_six_actual_source_roles(stress_case, monkeypatch):
    sources = stress_case[2][5]
    real_open = cli._open_inputs

    @contextmanager
    def bound(paths):
        with real_open(paths) as handles:
            original = sources[:]
            assert len(original) == 4 and len(handles) == 6
            sources[:] = handles[:4]
            try:
                yield handles
            finally:
                sources[:] = original

    monkeypatch.setattr(cli, "_open_inputs", bound)
    yield


def readonly_arguments(stress_case):
    _, reviewed, case = stress_case
    # Existing helper copies ACTUAL in-memory SQL and closes only file-backed owners.
    # Its seven-role contract is unchanged. This test uses only first SIX output roles.
    _, seven_paths = fixture_arguments(case, (*cli.PATH_NAMES, "bundle-archive-db"))
    paths = seven_paths[:6]
    args: list[str] = []
    for name, path in zip(cli.PATH_NAMES, paths, strict=True):
        args.extend(("--" + name, path))
    args.extend(
        (
            "--build-id-pin",
            reviewed.build_id,
            "--archive-fingerprint",
            reviewed.expected_archive_fingerprint,
            "--revalidation-fingerprint",
            reviewed.evidence_fingerprint,
            "--shock-bps",
            "0",
            "--execute",
        )
    )
    return args, paths


def test_actual_cli_positive_grid_and_database_bytes_unchanged(stress_case, capsys):
    args, paths = readonly_arguments(stress_case)
    before = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths}
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "computed_current_native_research_iv_spot_stress"
    assert all(result[k] is True for k in cli.OBSERVATION_FLAGS)
    assert all(result[k] is False for k in cli.DENIAL_FLAGS)
    curve = result["accepted_study"]
    assert len(curve["points"]) == 1
    assert curve["points"][0]["shock_bps"] == 0
    assert curve["points"][0]["model_price_change"] == 0.0
    assert curve["points"][0]["values"] == curve["baseline"]
    assert not any(k in result for k in ("before", "after", "provisional_study", "repeated_study"))
    assert {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths} == before


def test_wrong_reviewed_revalidation_pin_exposes_no_provisional_curve(stress_case, capsys):
    args, _ = readonly_arguments(stress_case)
    args[args.index("--revalidation-fingerprint") + 1] = "0" * 64
    assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "review_required"
    assert result["accepted_study"] is None and result["evidence_fingerprint"] is None


def test_changed_source_not_hidden_by_old_good_study(stress_case, capsys):
    state, option = stress_case[2][-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    args, _ = readonly_arguments(stress_case)
    assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["accepted_study"] is None and result["evidence_fingerprint"] is None
    assert result["stress_results_reproduced"] is False


def test_failure_sanitized_without_partial_curve(stress_case, monkeypatch, capsys):
    args, _ = readonly_arguments(stress_case)
    real = service.build_native_research_iv_spot_stress

    def fail_after_actual_native(*args, **kwargs):
        value = real(*args, **kwargs)
        assert value.status == "computed_current_native_research_iv_spot_stress"
        raise RuntimeError("PRIVATE_AFTER_NATIVE_FAILURE")

    monkeypatch.setattr(service, "build_native_research_iv_spot_stress", fail_after_actual_native)
    assert cli.main(args) == 1
    captured = capsys.readouterr()
    assert "PRIVATE_AFTER_NATIVE_FAILURE" not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "status": "FAILED",
        "reason_code": "IV_SPOT_STRESS_INSPECTION_FAILED",
    }
