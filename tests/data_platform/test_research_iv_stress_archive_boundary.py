"""Actual native stress/kernel/ledger/store; existing lower source substitution unchanged.

Supplied for actual repository QA, not sandbox-executed or acquisition-native E2E.
"""

from dataclasses import asdict, replace
from typing import Any

import duckdb
import pytest
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

from nse_quant.data_platform import native_research_iv_spot_stress as native
from nse_quant.data_platform import research_iv_revalidation as current
from nse_quant.data_platform import research_iv_stress_archive as store
from nse_quant.data_platform.audit import AuditLedger, JobState


@pytest.fixture
def archive_stress_case(stress_case, tmp_path):
    _, reviewed, case = stress_case
    sources, gold, archive = case[5:8]
    path = tmp_path / "stress-observation.duckdb"
    target = duckdb.connect(str(path))

    def run(**changes):
        args: dict[str, Any] = dict(
            build_id_pin=reviewed.build_id,
            expected_archive_fingerprint=reviewed.expected_archive_fingerprint,
            expected_revalidation_fingerprint=reviewed.evidence_fingerprint,
            shocks_bps=(0,),
            actor_id="synthetic",
            code_revision="synthetic",
            initialize=True,
        )
        args.update(changes)
        return store.persist_research_iv_spot_stress(*sources, gold, archive, target, **args)

    yield run, target, path, case
    target.close()


def test_actual_native_invoked_after_running_audit_and_complete_dto_retained(
    archive_stress_case,
    monkeypatch,
):
    run, target, _, _ = archive_stress_case
    real = native.build_native_research_iv_spot_stress
    calls: list[native.NativeResearchIvSpotStress] = []

    def observe(*args, **kwargs):
        name = store._name(target, "medallion_audit", "job_events")
        assert target.execute(f"SELECT state FROM {name} ORDER BY event_index").fetchall() == [
            ("PLANNED",),
            ("RUNNING",),
        ]
        value = real(*args, **kwargs)
        calls.append(value)
        return value

    monkeypatch.setattr(native, "build_native_research_iv_spot_stress", observe)
    recorded = run()
    assert len(calls) == 1
    retained = store.record.decode(recorded.record_json)
    # Normalize tuple/list JSON representations only; no numerical rounding.
    assert store.record.canonical(retained["result"]) == store.record.canonical(asdict(calls[0]))
    assert recorded.recorded_native_status == "computed_current_native_research_iv_spot_stress"
    assert recorded.original_recording_checked and not recorded.current_source_checked
    assert not recorded.model_computation_rechecked and not recorded.publication_asserted
    assert not recorded.decision_eligibility_asserted
    assert recorded.build_id != retained["request"]["pins"][0]


def test_review_outcome_is_durably_retained_not_promoted(archive_stress_case):
    run, _, _, case = archive_stress_case
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    recorded = run()
    body = store.record.decode(recorded.record_json)
    assert recorded.recorded_native_status == "review_required"
    assert body["result"]["before"] is not None
    assert body["result"]["study"] is None
    assert not recorded.current_source_checked


def test_after_source_drift_retains_provisional_and_both_observations(
    archive_stress_case,
    monkeypatch,
):
    run, _, _, case = archive_stress_case
    real = current.revalidate_research_iv_build
    state, option = case[-2:]
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            state[option.source_assessment_revision_id] = replace(option, status="blocked")
        return value

    monkeypatch.setattr(current, "revalidate_research_iv_build", observe)
    recorded = run()
    body = store.record.decode(recorded.record_json)["result"]
    assert calls == 2 and body["status"] == "review_required"
    assert body["provisional_study"] is not None and body["study"] is None
    assert body["before"] is not None and body["after"] is not None
    assert body["evidence_fingerprint"] is None


def test_no_retry_preserves_original_row_clock_and_audit(archive_stress_case):
    run, target, _, _ = archive_stress_case
    first = run()
    before = store._snapshot(target)
    with pytest.raises(store.IvStressArchiveReviewRequired, match="EXISTS_NO_RETRY"):
        run(initialize=False)
    assert store._snapshot(target) == before
    assert store.read_research_iv_spot_stress_archive(target, build_id_pin=first.build_id) == first


def test_native_exception_no_domain_record_failed_obligation_not_healed(
    archive_stress_case,
    monkeypatch,
):
    run, target, _, _ = archive_stress_case

    def fail(*args, **kwargs):
        raise OSError("synthetic native failure")

    monkeypatch.setattr(native, "build_native_research_iv_spot_stress", fail)
    with pytest.raises(OSError, match="synthetic native failure"):
        run()
    name = store._name(target, "gold", store.TABLE)
    assert target.execute(f"SELECT * FROM {name}").fetchall() == []
    with pytest.raises(store.IvStressArchiveReviewRequired, match="UNLINKED_JOB"):
        run(initialize=False)


def test_domain_commit_is_not_final_audit_success(archive_stress_case, monkeypatch):
    run, target, _, _ = archive_stress_case
    real = AuditLedger.transition

    def fail_final(self, job, state, reason_code=None):
        if self.conn is target and state == JobState.SUCCEEDED:
            raise OSError("synthetic final audit failure")
        return real(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail_final)
    with pytest.raises(OSError, match="synthetic final audit failure"):
        run()
    name = store._name(target, "gold", store.TABLE)
    row = target.execute(f"SELECT build_id FROM {name}").fetchone()
    assert row is not None
    with pytest.raises(store.IvStressArchiveReviewRequired, match="UNLINKED_JOB"):
        store.read_research_iv_spot_stress_archive(target, build_id_pin=row[0])


def test_original_reader_does_not_rerun_sources_or_pricing(archive_stress_case):
    run, target, _, case = archive_stress_case
    first = run()
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    assert store.read_research_iv_spot_stress_archive(target, build_id_pin=first.build_id) == first
    assert not first.current_source_checked and not first.model_computation_rechecked


def test_readonly_reopen_and_recording_clock_fingerprint(archive_stress_case):
    run, target, path, _ = archive_stress_case
    first = run()
    name = store._name(target, "gold", store.TABLE)
    target.execute(f"UPDATE {name} SET recorded_at=recorded_at+INTERVAL '1 second'")
    changed = store.read_research_iv_spot_stress_archive(target, build_id_pin=first.build_id)
    assert changed.record_json == first.record_json
    assert changed.evidence_fingerprint != first.evidence_fingerprint
    target.close()
    with duckdb.connect(str(path), read_only=True) as readonly:
        assert (
            store.read_research_iv_spot_stress_archive(
                readonly,
                build_id_pin=first.build_id,
            )
            == changed
        )


def test_orphan_events_block_original_recording(archive_stress_case):
    run, target, _, _ = archive_stress_case
    first = run()
    name = store._name(target, "medallion_audit", "job_events")
    target.execute(f"INSERT INTO {name} VALUES ('orphan',1,'FAILED',current_timestamp,NULL)")
    with pytest.raises(store.IvStressArchiveReviewRequired, match="ORPHAN_EVENTS"):
        store.read_research_iv_spot_stress_archive(target, build_id_pin=first.build_id)


def test_same_live_output_alias_rejected_before_initialization(archive_stress_case, stress_case):
    _, target, _, case = archive_stress_case
    _, reviewed, _ = stress_case
    sources, gold, archive = case[5:8]
    cursor = target.cursor()
    assert cursor is not target
    row = target.execute("SELECT current_database()").fetchone()
    assert row is not None
    cursor.execute('USE "' + str(row[0]).replace('"', '""') + '"')
    try:
        with pytest.raises(ValueError, match="SEPARATE_OUTPUT_REQUIRED"):
            store.persist_research_iv_spot_stress(
                cursor,
                *sources[1:],
                gold,
                archive,
                target,
                build_id_pin=reviewed.build_id,
                expected_archive_fingerprint=reviewed.expected_archive_fingerprint,
                expected_revalidation_fingerprint=reviewed.evidence_fingerprint,
                shocks_bps=(0,),
                actor_id="synthetic",
                code_revision="synthetic",
                initialize=True,
            )
        assert target.execute("SELECT 1").fetchone() == (1,)
    finally:
        cursor.close()
