"""Actual capture/audit/plan/stage integration with existing lower source substitute.

Supplied for repository QA; not sandbox-executed, not native acquisition E2E.
"""

import hashlib
from typing import Any

import duckdb
import pytest
from test_research_iv_recovery_plan_boundary import archive_case as archive_case
from test_research_iv_recovery_plan_boundary import artifact_case as artifact_case
from test_research_iv_recovery_plan_boundary import bundle_case as bundle_case
from test_research_iv_recovery_plan_boundary import current_bundle_case as current_bundle_case
from test_research_iv_recovery_plan_boundary import current_stage_case as current_stage_case
from test_research_iv_recovery_plan_boundary import revalidation_case as revalidation_case
from test_research_iv_recovery_plan_boundary import scenario as scenario
from test_research_iv_recovery_plan_boundary import setup as setup
from test_research_iv_recovery_plan_boundary import stage_case as stage_case
from test_research_iv_recovery_plan_boundary import writer as writer

from nse_quant.data_platform import research_iv_recovery_capture as store
from nse_quant.data_platform import research_iv_recovery_plan as native
from nse_quant.data_platform.audit import AuditLedger, JobState


@pytest.fixture
def capture_case(current_stage_case, tmp_path):
    _, staging, receipt, reviewed, root, _ = current_stage_case
    path = tmp_path / "recovery-capture.duckdb"
    target = duckdb.connect(str(path))

    def run(**changes):
        plan = native.plan_research_iv_stage_recovery(
            staging,
            stage_build_id_pin=receipt["build_id"],
            expected_stage_fingerprint=reviewed.evidence_fingerprint,
            artifact_root=root,
        )
        args: dict[str, Any] = dict(
            stage_build_id_pin=receipt["build_id"],
            expected_stage_fingerprint=reviewed.evidence_fingerprint,
            expected_plan_fingerprint=plan.evidence_fingerprint,
            artifact_root=root,
            actor_id="synthetic",
            code_revision="synthetic",
            initialize=True,
        )
        args.update(changes)
        return store.capture_research_iv_recovery(staging, target, **args)

    yield run, target, path, root
    target.close()


def test_two_actual_plans_and_running_audit_before_each(capture_case, monkeypatch):
    run, target, _, _ = capture_case
    real = native.plan_research_iv_stage_recovery
    observed: list[native.ResearchIvRecoveryPlan] = []

    def observe(*args, **kwargs):
        value = real(*args, **kwargs)
        # The test helper performs one explicit review BEFORE writer initialization.
        tables = target.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_catalog=current_database()"
        ).fetchall()
        if tables:
            name = store._name(target, "medallion_audit", "job_events")
            assert [
                r[0]
                for r in target.execute(f"SELECT state FROM {name} ORDER BY event_index").fetchall()
            ] == ["PLANNED", "RUNNING"]
            observed.append(value)
        return value

    monkeypatch.setattr(native, "plan_research_iv_stage_recovery", observe)
    value = run()
    assert len(observed) == 2 and observed[0] == observed[1]
    assert store.decode(value.record_json)["plan"]["status"] == "reconciled_retain_only"
    assert value.original_recording_checked and not value.current_reconciliation_checked
    assert not value.recovery_execution_authorized and not value.publication_asserted
    assert not value.decision_eligibility_asserted


def test_review_plan_is_recorded_as_review_not_authorization(capture_case):
    run, _, _, root = capture_case
    raw = b"synthetic foreign ownership unknown"
    path = root / (hashlib.sha256(raw).hexdigest() + ".research-iv.json")
    path.write_bytes(raw)
    value = run()
    plan = store.decode(value.record_json)["plan"]
    assert plan["status"] == "review_required"
    assert not plan["orphan_status_determined"] and not plan["recovery_execution_authorized"]
    assert path.read_bytes() == raw


def test_repeat_rejected_without_changing_original(capture_case):
    run, target, _, _ = capture_case
    first = run()
    before = store._snapshot(target)
    with pytest.raises(store.IvRecoveryCaptureReviewRequired, match="EXISTS_NO_RETRY"):
        run(initialize=False)
    assert store._snapshot(target) == before
    assert store.read_research_iv_recovery_capture(target, build_id_pin=first.build_id) == first


def test_wrong_plan_pin_records_failed_obligation_and_blocks_retry(capture_case):
    run, target, _, _ = capture_case
    with pytest.raises(ValueError, match="REVIEWED_PLAN_CHANGED"):
        run(expected_plan_fingerprint="0" * 64)
    table = store._name(target, "gold", store.TABLE)
    assert target.execute(f"SELECT * FROM {table}").fetchall() == []
    with pytest.raises(store.IvRecoveryCaptureReviewRequired, match="OBLIGATION_FAILED"):
        run(initialize=False)


def test_domain_commit_does_not_imply_final_audit_success(capture_case, monkeypatch):
    run, target, _, _ = capture_case
    real = AuditLedger.transition

    def fail_final(self, job_id, state, reason_code=None):
        if self.conn is target and state == JobState.SUCCEEDED:
            raise OSError("synthetic final audit failure")
        return real(self, job_id, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail_final)
    with pytest.raises(OSError, match="synthetic final audit failure"):
        run()
    table = store._name(target, "gold", store.TABLE)
    row = target.execute(f"SELECT build_id FROM {table}").fetchone()
    assert row is not None
    with pytest.raises(store.IvRecoveryCaptureReviewRequired, match="OBLIGATION_FAILED"):
        store.read_research_iv_recovery_capture(target, build_id_pin=row[0])


def test_reader_is_recording_only_even_after_artifact_change(capture_case):
    run, target, _, root = capture_case
    value = run()
    for path in root.iterdir():
        path.write_bytes(b"synthetic changed artifact")
    reread = store.read_research_iv_recovery_capture(target, build_id_pin=value.build_id)
    assert reread == value
    assert not reread.current_reconciliation_checked


def test_readonly_reopen_and_clock_mutation_changes_evidence(capture_case):
    run, target, path, _ = capture_case
    first = run()
    table = store._name(target, "gold", store.TABLE)
    target.execute(f"UPDATE {table} SET recorded_at=recorded_at+INTERVAL '1 second'")
    changed = store.read_research_iv_recovery_capture(target, build_id_pin=first.build_id)
    assert changed.evidence_fingerprint != first.evidence_fingerprint
    assert changed.record_json == first.record_json
    target.close()
    with duckdb.connect(str(path), read_only=True) as readonly:
        assert (
            store.read_research_iv_recovery_capture(readonly, build_id_pin=first.build_id)
            == changed
        )


def test_orphan_audit_event_invalidates_record(capture_case):
    run, target, _, _ = capture_case
    first = run()
    name = store._name(target, "medallion_audit", "job_events")
    target.execute(f"INSERT INTO {name} VALUES ('missing',1,'FAILED',current_timestamp,NULL)")
    with pytest.raises(store.IvRecoveryCaptureReviewRequired, match="ORPHAN_EVENTS"):
        store.read_research_iv_recovery_capture(target, build_id_pin=first.build_id)


def test_actual_plan_drift_between_calls_fails_without_domain_record(capture_case, monkeypatch):
    run, target, _, root = capture_case
    real = native.plan_research_iv_stage_recovery
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        # First is the caller's explicit review; second is the writer's first call.
        if calls == 2:
            raw = b"synthetic artifact added between native plans"
            path = root / (hashlib.sha256(raw).hexdigest() + ".research-iv.json")
            path.write_bytes(raw)
        return value

    monkeypatch.setattr(native, "plan_research_iv_stage_recovery", observe)
    with pytest.raises(ValueError, match="REVIEWED_PLAN_CHANGED"):
        run()
    assert calls == 3
    table = store._name(target, "gold", store.TABLE)
    assert target.execute(f"SELECT * FROM {table}").fetchall() == []


def test_second_native_exception_has_no_accepted_partial(capture_case, monkeypatch):
    run, target, _, _ = capture_case
    real = native.plan_research_iv_stage_recovery
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("synthetic second native failure")
        return real(*args, **kwargs)

    monkeypatch.setattr(native, "plan_research_iv_stage_recovery", observe)
    with pytest.raises(OSError, match="synthetic second native failure"):
        run()
    table = store._name(target, "gold", store.TABLE)
    assert target.execute(f"SELECT * FROM {table}").fetchall() == []
    name = store._name(target, "medallion_audit", "job_events")
    rows = target.execute(f"SELECT state FROM {name} ORDER BY event_index").fetchall()
    assert rows == [("PLANNED",), ("RUNNING",), ("FAILED",)]


def test_same_live_target_cursor_is_rejected_before_initialization(capture_case):
    _, target, _, root = capture_case
    cursor = target.cursor()
    assert cursor is not target
    row = target.execute("SELECT current_database()").fetchone()
    assert row is not None
    cursor.execute('USE "' + str(row[0]).replace('"', '""') + '"')
    try:
        with pytest.raises(ValueError, match="SEPARATE_DATABASE_REQUIRED"):
            store.capture_research_iv_recovery(
                cursor,
                target,
                stage_build_id_pin="a" * 64,
                expected_stage_fingerprint="b" * 64,
                expected_plan_fingerprint="c" * 64,
                artifact_root=root,
                actor_id="synthetic",
                code_revision="synthetic",
                initialize=True,
            )
        assert target.execute("SELECT 1").fetchone() == (1,)
    finally:
        cursor.close()
