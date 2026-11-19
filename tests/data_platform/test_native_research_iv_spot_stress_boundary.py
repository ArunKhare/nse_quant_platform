"""Actual native source/IV/kernel calls with existing lower source substitute.

Repository tests supplied, not sandbox-executed, not native acquisition E2E.
"""

from dataclasses import asdict, replace
from typing import Any

import pytest
from test_research_iv_current_stage_boundary import archive_case as archive_case
from test_research_iv_current_stage_boundary import artifact_case as artifact_case
from test_research_iv_current_stage_boundary import bundle_case as bundle_case
from test_research_iv_current_stage_boundary import current_bundle_case as current_bundle_case
from test_research_iv_current_stage_boundary import current_stage_case as current_stage_case
from test_research_iv_current_stage_boundary import revalidation_case as revalidation_case
from test_research_iv_current_stage_boundary import scenario as scenario
from test_research_iv_current_stage_boundary import setup as setup
from test_research_iv_current_stage_boundary import stage_case as stage_case
from test_research_iv_current_stage_boundary import writer as writer

from nse_quant.data_platform import native_research_iv_spot_stress as service
from nse_quant.data_platform import research_iv_revalidation as native


@pytest.fixture
def stress_case(current_stage_case):
    run_stage, _, _, _, _, case = current_stage_case
    checked = run_stage()
    assert checked.status == "matched_current_research_iv_stage"
    assert checked.fresh_before is not None and checked.fresh_before.fresh_before is not None
    reviewed = checked.fresh_before.fresh_before.first_pass[0]
    sources, gold, archive = case[5:8]

    def run(**changes):
        args: dict[str, Any] = dict(
            build_id_pin=reviewed.build_id,
            expected_archive_fingerprint=reviewed.expected_archive_fingerprint,
            expected_revalidation_fingerprint=reviewed.evidence_fingerprint,
            shocks_bps=(0,),
        )
        args.update(changes)
        return service.build_native_research_iv_spot_stress(*sources, gold, archive, **args)

    return run, reviewed, case


def test_actual_revalidations_and_kernel_grid_reproduce(stress_case, monkeypatch):
    run, reviewed, _ = stress_case
    real = native.revalidate_research_iv_build
    calls: list[native.ResearchIvRevalidation] = []

    def observe(*args, **kwargs):
        value = real(*args, **kwargs)
        calls.append(value)
        return value

    monkeypatch.setattr(native, "revalidate_research_iv_build", observe)
    value = run()
    assert len(calls) == 2
    assert value.status == "computed_current_native_research_iv_spot_stress"
    assert value.before == value.after == reviewed
    assert value.study == value.provisional_study == value.repeated_study
    assert value.study is not None
    assert value.study.points[0].model_price_change == 0.0
    assert value.current_source_checked and value.exact_native_observations_matched
    assert value.stress_results_reproduced and value.evidence_fingerprint is not None
    assert value.source_option_event_ts == reviewed.fresh_before.source_option_event_ts
    assert value.source_spot_event_ts == reviewed.fresh_before.source_spot_event_ts
    for key in (
        "portfolio_pnl_asserted",
        "volatility_response_modelled",
        "option_underlying_identity_binding_verified",
        "scenario_terms_authoritative",
        "model_suitability_verified",
        "source_acquisition_authenticity_asserted",
        "availability_evidence_verified",
        "historical_validity_asserted",
        "publication_asserted",
        "decision_eligibility_asserted",
        "atomic_cross_database_snapshot_asserted",
    ):
        assert asdict(value)[key] is False
    assert value.canonical_contract_id is None and value.event_ts is None
    assert value.published_at is None


def test_wrong_reviewed_native_pin_stops_before_stress_kernel(stress_case, monkeypatch):
    run = stress_case[0]

    def forbidden(*args, **kwargs):
        raise AssertionError("Unreviewed native input reached stress kernel")

    monkeypatch.setattr(service, "compute_research_iv_spot_stress", forbidden)
    value = run(expected_revalidation_fingerprint="0" * 64)
    assert value.status == "review_required" and value.study is None
    assert value.provisional_study is None and value.evidence_fingerprint is None


def test_changed_source_before_pricing_returns_review_not_old_good(stress_case):
    run, _, case = stress_case
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    value = run()
    assert value.status == "review_required" and value.study is None
    assert value.before.status == "review_required" and value.provisional_study is None


def test_after_source_drift_retains_provisional_not_accepted_study(stress_case, monkeypatch):
    run, _, case = stress_case
    real = native.revalidate_research_iv_build
    calls = 0
    state, option = case[-2:]

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            state[option.source_assessment_revision_id] = replace(option, status="blocked")
        return value

    monkeypatch.setattr(native, "revalidate_research_iv_build", observe)
    value = run()
    assert calls == 2 and value.status == "review_required"
    assert value.provisional_study is not None and value.after.status == "review_required"
    assert value.study is None and value.evidence_fingerprint is None
    assert not value.exact_native_observations_matched


def test_second_native_exception_has_no_partial_return(stress_case, monkeypatch):
    run = stress_case[0]
    real = native.revalidate_research_iv_build
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic second native failure")
        return real(*args, **kwargs)

    monkeypatch.setattr(native, "revalidate_research_iv_build", observe)
    with pytest.raises(OSError, match="synthetic second native failure"):
        run()
    assert calls == 2


def test_observation_bound_rejects_not_prefix_acceptance(stress_case, monkeypatch):
    monkeypatch.setattr(service, "MAX_NATIVE_BYTES", 1)
    with pytest.raises(ValueError, match="OBSERVATION_BYTE_LIMIT"):
        stress_case[0]()


def test_native_stress_does_not_write_source_or_archive_tables(stress_case):
    run, _, case = stress_case
    sources, gold, archive = case[5:8]

    def snapshot(conn):
        row = conn.execute("SELECT current_database()").fetchone()
        assert row is not None
        tables = conn.execute(
            "SELECT table_schema,table_name FROM information_schema.tables "
            "WHERE table_catalog=current_database() ORDER BY table_schema,table_name"
        ).fetchall()
        result: list[object] = []
        for schema, table in tables:
            quoted = ".".join(
                '"' + str(v).replace('"', '""') + '"' for v in (row[0], schema, table)
            )
            rows = conn.execute(f"SELECT * FROM {quoted} ORDER BY ALL").fetchall()
            result.append((schema, table, rows))
        return result

    connections = (*sources, gold, archive)
    before = [snapshot(conn) for conn in connections]
    assert run().status == "computed_current_native_research_iv_spot_stress"
    assert [snapshot(conn) for conn in connections] == before
