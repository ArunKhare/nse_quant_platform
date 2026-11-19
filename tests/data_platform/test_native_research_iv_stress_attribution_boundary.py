"""Actual archive currentness/model/study attribution, existing lower source substitute unchanged.

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

from nse_quant.data_platform import native_research_iv_stress_attribution as service
from nse_quant.data_platform import research_iv_stress_archive as store
from nse_quant.data_platform import research_iv_stress_archive_record as record
from nse_quant.data_platform import research_iv_stress_archive_revalidation as current
from nse_quant.data_platform.audit import AuditLedger


@pytest.fixture
def attribution_case(current_stress_case):
    _, target, recorded, _, case = current_stress_case
    sources, gold, archive = case[5:8]

    def run(**changes):
        args: dict[str, Any] = dict(
            stress_record_id_pin=recorded.build_id,
            expected_recording_fingerprint=recorded.evidence_fingerprint,
        )
        args.update(changes)
        return service.build_native_research_iv_stress_attribution(
            *sources,
            gold,
            archive,
            target,
            **args,
        )

    return run, target, case


def test_actual_contexts_and_arithmetic_reproduce_without_archive_writes(
    attribution_case,
    monkeypatch,
):
    run, target, _ = attribution_case
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
    assert value.status == "computed_current_native_research_iv_stress_attribution"
    assert value.before == calls[0] and value.after == calls[1]
    assert value.attribution == value.provisional_attribution == value.repeated_attribution
    assert value.attribution is not None and value.evidence_fingerprint is not None
    part = value.attribution.points[0].decomposition
    assert part.spot_change_float == part.delta_component == part.gamma_component == 0.0
    assert part.second_order_residual == part.reconstruction_roundoff == 0.0
    assert value.current_context_matched and value.attribution_reproduced
    assert store._snapshot(target) == fingerprint
    for key in (*record.DENIALS, "approximation_accuracy_certified"):
        assert getattr(value, key) is False
    assert value.canonical_contract_id is None and value.event_ts is None
    assert value.published_at is None
    assert value.source_option_event_ts == calls[0].source_option_event_ts
    assert value.source_spot_event_ts == calls[0].source_spot_event_ts


def test_wrong_original_review_stops_before_attribution(attribution_case, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unreviewed context reached attribution")

    monkeypatch.setattr(service, "attribute_research_iv_spot_stress", forbidden)
    value = attribution_case[0](expected_recording_fingerprint="0" * 64)
    assert value.status == "review_required" and value.attribution is None
    assert value.provisional_attribution is None and value.evidence_fingerprint is None


def test_after_source_drift_retains_provisional_not_accepted(attribution_case, monkeypatch):
    run, _, case = attribution_case
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
    assert value.provisional_attribution is not None and value.after.status == "review_required"
    assert value.attribution is None and value.evidence_fingerprint is None
    assert not value.current_context_matched


def test_changed_source_before_attribution_has_no_provisional(attribution_case):
    run, _, case = attribution_case
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    value = run()
    assert value.status == "review_required" and value.provisional_attribution is None
    assert value.attribution is None and value.evidence_fingerprint is None


def test_second_context_exception_never_returns_partial(attribution_case, monkeypatch):
    real = current.revalidate_research_iv_spot_stress_archive
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic second context failure")
        return real(*args, **kwargs)

    monkeypatch.setattr(current, "revalidate_research_iv_spot_stress_archive", observe)
    with pytest.raises(OSError, match="synthetic second context failure"):
        attribution_case[0]()
    assert calls == 2


def test_after_audit_failure_does_not_accept_partial_attribution(attribution_case, monkeypatch):
    run, target, _ = attribution_case
    real = current.revalidate_research_iv_spot_stress_archive
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            AuditLedger(target).plan_job(
                command_name=store.COMMAND,
                actor_id="synthetic",
                scope_ref="f" * 64,
                code_revision="synthetic",
                config_hash=record.sha(record.canonical(record.DEFINITION).encode()),
            )
        return value

    monkeypatch.setattr(current, "revalidate_research_iv_spot_stress_archive", observe)
    value = run()
    assert value.provisional_attribution is not None and value.after.status == "review_required"
    assert value.attribution is None and value.evidence_fingerprint is None


def test_full_context_bound_no_prefix_acceptance(attribution_case, monkeypatch):
    monkeypatch.setattr(service, "MAX_CONTEXT_BYTES", 1)
    with pytest.raises(ValueError, match="CONTEXT_BYTE_LIMIT"):
        attribution_case[0]()
