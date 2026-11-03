"""Actual surface/native/current archive and seven-file CLI; lower source substitute unchanged.

Supplied for repository QA; not sandbox-run or acquisition-native E2E.
"""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from iv_bundle_inspection_fixture_files import bind_fixture_sources, fixture_arguments
from test_native_research_iv_spot_vol_surface_boundary import archive_case as archive_case
from test_native_research_iv_spot_vol_surface_boundary import (
    archive_stress_case as archive_stress_case,
)
from test_native_research_iv_spot_vol_surface_boundary import artifact_case as artifact_case
from test_native_research_iv_spot_vol_surface_boundary import bundle_case as bundle_case
from test_native_research_iv_spot_vol_surface_boundary import (
    current_bundle_case as current_bundle_case,
)
from test_native_research_iv_spot_vol_surface_boundary import (
    current_stage_case as current_stage_case,
)
from test_native_research_iv_spot_vol_surface_boundary import (
    current_stress_case as current_stress_case,
)
from test_native_research_iv_spot_vol_surface_boundary import revalidation_case as revalidation_case
from test_native_research_iv_spot_vol_surface_boundary import scenario as scenario
from test_native_research_iv_spot_vol_surface_boundary import setup as setup
from test_native_research_iv_spot_vol_surface_boundary import stage_case as stage_case
from test_native_research_iv_spot_vol_surface_boundary import stress_case as stress_case
from test_native_research_iv_spot_vol_surface_boundary import writer as writer

from nse_quant.data_platform import native_research_iv_spot_vol_surface as native
from nse_quant.data_platform import research_iv_spot_vol_surface_cli as cli


def readonly_arguments(target, recorded, path, case):
    _, paths = fixture_arguments(case, (*cli.PATH_NAMES[:6], "bundle-archive-db"))
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
            "--vol-shift-bps",
            "0",
            "--execute",
        )
    )
    return args, paths


@pytest.fixture
def cli_case(current_stress_case, monkeypatch):
    _, target, recorded, path, case = current_stress_case
    args, paths = readonly_arguments(target, recorded, path, case)
    with bind_fixture_sources(cli, case[5], monkeypatch):
        yield args, paths, recorded, case


def test_actual_positive_summary_no_database_changes(cli_case, capsys):
    args, paths, recorded, _ = cli_case
    before = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "computed_current_native_research_iv_spot_vol_surface"
    assert all(result[k] is True for k in cli.OBSERVATION_FLAGS)
    assert all(result[k] is False for k in cli.DENIAL_FLAGS)
    assert result["stress_record_id"] == recorded.build_id
    assert result["hypothetical_volatility_shift_assumed"] is True
    summary = result["accepted_surface_summary"]
    assert summary["spot_shocks_bps"] == summary["vol_shifts_bps"] == [0]
    assert summary["cell_count"] == 1
    column = summary["column_summaries"][0]
    assert column["volatility_hex"] == summary["base_volatility_hex"]
    assert column["full_model_price_change_min"] == column["full_model_price_change_max"] == 0.0
    assert column["interaction_change_min"] == column["interaction_change_max"] == 0.0
    assert column["reconstruction_roundoff_abs_max"] == 0.0
    assert not any(k in result for k in ("before", "after", "provisional_surface", "cells"))
    assert {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths} == before


def test_wrong_review_pin_stops_surface_pricing(cli_case, monkeypatch, capsys):
    args = cli_case[0]
    args[args.index("--recording-fingerprint") + 1] = "0" * 64

    def forbidden(*args, **kwargs):
        raise AssertionError("Unreviewed record reached surface pricing")

    monkeypatch.setattr(native, "compute_research_iv_spot_vol_surface", forbidden)
    assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["accepted_surface_summary"] is None and result["evidence_fingerprint"] is None


def test_changed_source_does_not_reuse_old_surface(cli_case, capsys):
    args, _, _, case = cli_case
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["accepted_surface_summary"] is None and result["evidence_fingerprint"] is None
    assert result["surface_reproduced"] is False
    assert result["volatility_response_modelled"] is False


def test_recorded_review_cannot_be_upgraded(archive_stress_case, monkeypatch, capsys):
    execute, target, path, case = archive_stress_case
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    recorded = execute()
    state[option.source_assessment_revision_id] = option
    args, _ = readonly_arguments(target, recorded, path, case)

    def forbidden(*args, **kwargs):
        raise AssertionError("Recorded review reached surface pricing")

    monkeypatch.setattr(native, "compute_research_iv_spot_vol_surface", forbidden)
    with bind_fixture_sources(cli, case[5], monkeypatch):
        assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["accepted_surface_summary"] is None and result["current_source_checked"] is False


def test_post_native_exception_sanitized_without_partial_surface(cli_case, monkeypatch, capsys):
    real = native.build_native_research_iv_spot_vol_surface

    def fail_after_actual(*args, **kwargs):
        value = real(*args, **kwargs)
        assert value.status == "computed_current_native_research_iv_spot_vol_surface"
        raise RuntimeError("PRIVATE_POST_SURFACE_EXCEPTION")

    monkeypatch.setattr(native, "build_native_research_iv_spot_vol_surface", fail_after_actual)
    assert cli.main(cli_case[0]) == 1
    captured = capsys.readouterr()
    assert "PRIVATE_POST_SURFACE_EXCEPTION" not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "status": "FAILED",
        "reason_code": "IV_SPOT_VOL_SURFACE_INSPECTION_FAILED",
    }
