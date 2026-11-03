"""Actual current evidence, full BSM surface and joint arithmetic.

Existing lower source substitute unchanged.

Supplied for repository QA; not sandbox-run or acquisition-native E2E.
"""

from dataclasses import replace
from typing import Any

import pytest
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
from test_native_research_iv_spot_vol_surface_boundary import (
    revalidation_case as revalidation_case,
)
from test_native_research_iv_spot_vol_surface_boundary import scenario as scenario
from test_native_research_iv_spot_vol_surface_boundary import setup as setup
from test_native_research_iv_spot_vol_surface_boundary import stage_case as stage_case
from test_native_research_iv_spot_vol_surface_boundary import stress_case as stress_case
from test_native_research_iv_spot_vol_surface_boundary import surface_case as surface_case
from test_native_research_iv_spot_vol_surface_boundary import writer as writer

from nse_quant.data_platform import native_research_iv_joint_attribution as service
from nse_quant.data_platform import research_iv_stress_archive as store
from nse_quant.data_platform import research_iv_stress_archive_record as record
from nse_quant.data_platform import research_iv_stress_archive_revalidation as current


@pytest.fixture
def joint_case(surface_case):
    execute_surface, target, case = surface_case
    baseline = execute_surface()
    assert baseline.status == "computed_current_native_research_iv_spot_vol_surface"
    sources, gold, archive = case[5:8]

    def run(**changes):
        args: dict[str, Any] = dict(
            stress_record_id_pin=baseline.stress_record_id,
            expected_recording_fingerprint=baseline.expected_recording_fingerprint,
            vol_shifts_bps=(0,),
        )
        args.update(changes)
        return service.build_native_research_iv_joint_attribution(
            *sources,
            gold,
            archive,
            target,
            **args,
        )

    return run, target, case


def test_actual_contexts_surfaces_and_joint_arithmetic_reproduce(joint_case, monkeypatch):
    run, target, _ = joint_case
    real = current.revalidate_research_iv_spot_stress_archive
    calls: list[current.ResearchIvCurrentStressArchive] = []

    def observe(*args, **kwargs):
        value = real(*args, **kwargs)
        calls.append(value)
        return value

    monkeypatch.setattr(current, "revalidate_research_iv_spot_stress_archive", observe)
    fingerprint = store._snapshot(target)
    value = run()
    assert len(calls) == 2 and calls[0] == calls[1]
    assert value.status == "computed_current_native_research_iv_joint_attribution"
    assert value.surface == value.provisional_surface == value.repeated_surface
    assert value.attribution == value.provisional_attribution == value.repeated_attribution
    assert value.attribution is not None and value.surface is not None
    part = value.attribution.cells[0]
    assert part.spot.delta_component == part.spot.gamma_component == 0.0
    assert part.joint.vega_component == part.joint.joint_residual == 0.0
    assert value.current_context_matched and value.surface_reproduced
    assert value.attribution_reproduced
    assert value.evidence_fingerprint is not None
    assert store._snapshot(target) == fingerprint
    for key in (*record.DENIALS, "approximation_accuracy_certified", "vanna_volga_included"):
        assert getattr(value, key) is False
    assert value.hypothetical_volatility_shift_assumed
    assert value.canonical_contract_id is None and value.event_ts is None
    assert value.published_at is None


def test_wrong_reviewed_pin_stops_all_joint_math(joint_case, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unreviewed record reached joint attribution")

    monkeypatch.setattr(service, "attribute_research_iv_spot_vol_surface", forbidden)
    value = joint_case[0](expected_recording_fingerprint="0" * 64)
    assert value.status == "review_required" and value.attribution is None and value.surface is None
    assert value.provisional_attribution is None and value.evidence_fingerprint is None


def test_initial_source_negative_has_no_provisional(joint_case):
    run, _, case = joint_case
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    value = run()
    assert value.status == "review_required" and value.provisional_surface is None
    assert value.attribution is None and value.evidence_fingerprint is None


def test_after_source_drift_keeps_diagnostics_not_accepted_output(joint_case, monkeypatch):
    run, _, case = joint_case
    real = current.revalidate_research_iv_spot_stress_archive
    state, option = case[-2:]
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            state[option.source_assessment_revision_id] = replace(option, status="blocked")
        return value

    monkeypatch.setattr(current, "revalidate_research_iv_spot_stress_archive", observe)
    value = run()
    assert calls == 2 and value.status == "review_required"
    assert value.provisional_surface is not None and value.provisional_attribution is not None
    assert value.after.status == "review_required"
    assert value.surface is None and value.attribution is None
    assert value.evidence_fingerprint is None


def test_second_context_exception_has_no_partial_return(joint_case, monkeypatch):
    real = current.revalidate_research_iv_spot_stress_archive
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic second joint context failure")
        return real(*args, **kwargs)

    monkeypatch.setattr(current, "revalidate_research_iv_spot_stress_archive", observe)
    with pytest.raises(OSError, match="synthetic second joint context failure"):
        joint_case[0]()
    assert calls == 2


def test_invalid_vol_grid_stops_before_current_native_work(joint_case, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid request reached native evidence")

    monkeypatch.setattr(current, "revalidate_research_iv_spot_stress_archive", forbidden)
    with pytest.raises(ValueError, match="SORTED_UNIQUE"):
        joint_case[0](vol_shifts_bps=(1, 0))


def test_context_limit_never_accepts_prefix(joint_case, monkeypatch):
    monkeypatch.setattr(service, "MAX_CONTEXT_BYTES", 1)
    with pytest.raises(ValueError, match="CONTEXT_BYTE_LIMIT"):
        joint_case[0]()
