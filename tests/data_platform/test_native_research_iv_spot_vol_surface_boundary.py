"""Actual current archive/model/surface with original lower source substitute unchanged.

Supplied for repository QA; not sandbox-executed or acquisition-native E2E.
"""

from dataclasses import replace
from typing import Any

import pytest
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

from nse_quant.data_platform import native_research_iv_spot_vol_surface as service
from nse_quant.data_platform import research_iv_stress_archive as store
from nse_quant.data_platform import research_iv_stress_archive_record as record
from nse_quant.data_platform import research_iv_stress_archive_revalidation as current


@pytest.fixture
def surface_case(current_stress_case):
    _, target, recorded, _, case = current_stress_case
    sources, gold, archive = case[5:8]

    def run(**changes):
        args: dict[str, Any] = dict(
            stress_record_id_pin=recorded.build_id,
            expected_recording_fingerprint=recorded.evidence_fingerprint,
            vol_shifts_bps=(0,),
        )
        args.update(changes)
        return service.build_native_research_iv_spot_vol_surface(
            *sources,
            gold,
            archive,
            target,
            **args,
        )

    return run, target, case


def test_actual_current_contexts_and_surface_reproduce_without_archive_writes(
    surface_case,
    monkeypatch,
):
    run, target, _ = surface_case
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
    assert value.status == "computed_current_native_research_iv_spot_vol_surface"
    assert value.surface == value.provisional_surface == value.repeated_surface
    assert value.surface is not None and value.evidence_fingerprint is not None
    assert len(value.surface.cells) == 1 and value.surface.cells[0].full_model_price_change == 0.0
    assert value.current_context_matched and value.surface_reproduced
    assert store._snapshot(target) == fingerprint
    assert value.hypothetical_volatility_shift_assumed
    for key in record.DENIALS:
        assert getattr(value, key) is False
    assert value.event_ts is None and value.published_at is None
    assert value.canonical_contract_id is None


def test_wrong_review_pin_stops_surface_pricing(surface_case, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unreviewed record reached surface pricing")

    monkeypatch.setattr(service, "compute_research_iv_spot_vol_surface", forbidden)
    value = surface_case[0](expected_recording_fingerprint="0" * 64)
    assert value.status == "review_required" and value.surface is None
    assert value.provisional_surface is None and value.evidence_fingerprint is None


def test_initial_source_failure_not_reused(surface_case):
    run, _, case = surface_case
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    value = run()
    assert value.status == "review_required" and value.provisional_surface is None
    assert value.surface is None and value.evidence_fingerprint is None


def test_after_source_drift_retains_provisional_not_accepted(surface_case, monkeypatch):
    run, _, case = surface_case
    state, option = case[-2:]
    real = current.revalidate_research_iv_spot_stress_archive
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
    assert value.provisional_surface is not None and value.after.status == "review_required"
    assert value.surface is None and value.evidence_fingerprint is None


def test_second_context_exception_has_no_partial_output(surface_case, monkeypatch):
    real = current.revalidate_research_iv_spot_stress_archive
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic second surface context failure")
        return real(*args, **kwargs)

    monkeypatch.setattr(current, "revalidate_research_iv_spot_stress_archive", observe)
    with pytest.raises(OSError, match="synthetic second surface context failure"):
        surface_case[0]()
    assert calls == 2


def test_invalid_request_grid_stops_before_native_context(surface_case, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid vol grid reached current context")

    monkeypatch.setattr(current, "revalidate_research_iv_spot_stress_archive", forbidden)
    with pytest.raises(ValueError, match="SORTED_UNIQUE"):
        surface_case[0](vol_shifts_bps=(1, 0))


def test_context_bound_rejects_without_prefix(surface_case, monkeypatch):
    monkeypatch.setattr(service, "MAX_CONTEXT_BYTES", 1)
    with pytest.raises(ValueError, match="CONTEXT_BYTE_LIMIT"):
        surface_case[0]()
