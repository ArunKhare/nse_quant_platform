"""Actual native attribution/contexts/model and seven-file CLI, lower source substitute unchanged.

Supplied for local QA; not sandbox-executed or acquisition-native E2E.
"""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from iv_bundle_inspection_fixture_files import bind_fixture_sources, fixture_arguments
from test_native_research_iv_stress_attribution_boundary import archive_case as archive_case
from test_native_research_iv_stress_attribution_boundary import (
    archive_stress_case as archive_stress_case,
)
from test_native_research_iv_stress_attribution_boundary import artifact_case as artifact_case
from test_native_research_iv_stress_attribution_boundary import bundle_case as bundle_case
from test_native_research_iv_stress_attribution_boundary import (
    current_bundle_case as current_bundle_case,
)
from test_native_research_iv_stress_attribution_boundary import (
    current_stage_case as current_stage_case,
)
from test_native_research_iv_stress_attribution_boundary import (
    current_stress_case as current_stress_case,
)
from test_native_research_iv_stress_attribution_boundary import (
    revalidation_case as revalidation_case,
)
from test_native_research_iv_stress_attribution_boundary import scenario as scenario
from test_native_research_iv_stress_attribution_boundary import setup as setup
from test_native_research_iv_stress_attribution_boundary import stage_case as stage_case
from test_native_research_iv_stress_attribution_boundary import stress_case as stress_case
from test_native_research_iv_stress_attribution_boundary import writer as writer

from nse_quant.data_platform import native_research_iv_stress_attribution as native
from nse_quant.data_platform import research_iv_stress_attribution_cli as cli


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
            "--execute",
        )
    )
    return args, paths


@pytest.fixture
def cli_case(current_stress_case, monkeypatch):
    _, target, recorded, path, case = current_stress_case
    args, paths = readonly_arguments(target, recorded, path, case)
    # Reuse helper unchanged: exact identity assertion sees actual reopened read-only handles.
    with bind_fixture_sources(cli, case[5], monkeypatch):
        yield args, paths, recorded, case


def test_actual_cli_attribution_components_without_file_changes(cli_case, capsys):
    args, paths, recorded, _ = cli_case
    before = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "computed_current_native_research_iv_stress_attribution"
    assert all(result[k] is True for k in cli.OBSERVATION_FLAGS)
    assert all(result[k] is False for k in cli.DENIAL_FLAGS)
    assert result["stress_record_id"] == recorded.build_id
    accepted = result["accepted_attribution"]
    assert len(accepted["points"]) == 1
    point = accepted["points"][0]
    assert point["shock_bps"] == 0
    assert point["delta_component"] == point["gamma_component"] == 0.0
    assert point["second_order_residual"] == point["reconstruction_roundoff"] == 0.0
    assert not any(k in result for k in ("before", "after", "provisional_attribution"))
    assert {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths} == before


def test_wrong_reviewed_pin_stops_attribution(cli_case, monkeypatch, capsys):
    args = cli_case[0]
    args[args.index("--recording-fingerprint") + 1] = "0" * 64

    def forbidden(*args, **kwargs):
        raise AssertionError("Unreviewed context reached attribution")

    monkeypatch.setattr(native, "attribute_research_iv_spot_stress", forbidden)
    assert cli.main(args) == 2
    value = json.loads(capsys.readouterr().out)
    assert value["accepted_attribution"] is None and value["evidence_fingerprint"] is None


def test_changed_source_cannot_reuse_old_attribution(cli_case, capsys):
    args, _, _, case = cli_case
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    assert cli.main(args) == 2
    value = json.loads(capsys.readouterr().out)
    assert value["accepted_attribution"] is None and value["evidence_fingerprint"] is None
    assert value["attribution_reproduced"] is False
    assert value["approximation_accuracy_certified"] is False


def test_recorded_review_never_upgraded(archive_stress_case, monkeypatch, capsys):
    execute, target, path, case = archive_stress_case
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    recorded = execute()
    state[option.source_assessment_revision_id] = option
    args, _ = readonly_arguments(target, recorded, path, case)

    def forbidden(*args, **kwargs):
        raise AssertionError("Recorded review reached attribution")

    monkeypatch.setattr(native, "attribute_research_iv_spot_stress", forbidden)
    with bind_fixture_sources(cli, case[5], monkeypatch):
        assert cli.main(args) == 2
    value = json.loads(capsys.readouterr().out)
    assert value["accepted_attribution"] is None and value["current_source_checked"] is False


def test_exception_after_actual_native_attribution_is_sanitized(cli_case, monkeypatch, capsys):
    real = native.build_native_research_iv_stress_attribution

    def fail_after_actual(*args, **kwargs):
        result = real(*args, **kwargs)
        assert result.status == "computed_current_native_research_iv_stress_attribution"
        raise RuntimeError("PRIVATE_POST_ATTRIBUTION_EXCEPTION")

    monkeypatch.setattr(native, "build_native_research_iv_stress_attribution", fail_after_actual)
    assert cli.main(cli_case[0]) == 1
    captured = capsys.readouterr()
    assert "PRIVATE_POST_ATTRIBUTION_EXCEPTION" not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "status": "FAILED",
        "reason_code": "IV_STRESS_ATTRIBUTION_INSPECTION_FAILED",
    }
