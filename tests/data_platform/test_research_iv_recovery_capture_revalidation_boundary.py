"""Actual native capture/plan/stage/audit/files with existing lower source substitute.

Supplied for repository QA, not sandbox-executed or full acquisition-native E2E.
"""

import hashlib
import os
from dataclasses import asdict
from typing import Any

import duckdb
import pytest
from test_research_iv_recovery_capture_boundary import archive_case as archive_case
from test_research_iv_recovery_capture_boundary import artifact_case as artifact_case
from test_research_iv_recovery_capture_boundary import bundle_case as bundle_case
from test_research_iv_recovery_capture_boundary import capture_case as capture_case
from test_research_iv_recovery_capture_boundary import current_bundle_case as current_bundle_case
from test_research_iv_recovery_capture_boundary import current_stage_case as current_stage_case
from test_research_iv_recovery_capture_boundary import revalidation_case as revalidation_case
from test_research_iv_recovery_capture_boundary import scenario as scenario
from test_research_iv_recovery_capture_boundary import setup as setup
from test_research_iv_recovery_capture_boundary import stage_case as stage_case
from test_research_iv_recovery_capture_boundary import writer as writer

from nse_quant.data_platform import research_iv_recovery_capture as store
from nse_quant.data_platform import research_iv_recovery_capture_revalidation as service
from nse_quant.data_platform import research_iv_recovery_plan as native
from nse_quant.data_platform.audit import AuditLedger


@pytest.fixture
def current_capture_case(capture_case, current_stage_case):
    capture_run, capture, path, root = capture_case
    staging = current_stage_case[1]
    recorded = capture_run()

    def run(connection=None, **changes):
        args: dict[str, Any] = dict(
            capture_build_id_pin=recorded.build_id,
            expected_capture_fingerprint=recorded.evidence_fingerprint,
            artifact_root=root,
        )
        args.update(changes)
        return service.revalidate_research_iv_recovery_capture(
            staging,
            capture if connection is None else connection,
            **args,
        )

    return run, capture, recorded, root, path, staging


def test_actual_native_plans_reproduce_complete_record_and_no_writes(
    current_capture_case,
    monkeypatch,
):
    run, capture, recorded, _, _, staging = current_capture_case
    real = native.plan_research_iv_stage_recovery
    calls: list[native.ResearchIvRecoveryPlan] = []

    def observe(*args, **kwargs):
        value = real(*args, **kwargs)
        calls.append(value)
        return value

    monkeypatch.setattr(native, "plan_research_iv_stage_recovery", observe)
    captured_before = store._snapshot(capture)
    stage_tables = [
        store._name(staging, "medallion_audit", name)
        for name in ("dataset_contracts", "jobs", "job_events")
    ]
    stage_before = [
        staging.execute(f"SELECT * FROM {n} ORDER BY ALL").fetchall() for n in stage_tables
    ]
    value = run()
    assert len(calls) == 2 and calls[0] == calls[1]
    assert value.status == "matched_current_research_iv_recovery_capture"
    assert value.capture_before == value.capture_after == recorded
    assert value.fresh_before == calls[0] and value.fresh_after == calls[1]
    assert value.comparison is not None and value.comparison.all_plan_bytes_match
    assert value.archived_recording_verified and value.current_reconciliation_checked
    assert value.exact_recorded_plan_reproduced and value.capture_unchanged_observed
    assert value.plan_evidence_fingerprint == calls[0].evidence_fingerprint
    assert value.evidence_fingerprint is not None
    assert store._snapshot(capture) == captured_before
    assert [
        staging.execute(f"SELECT * FROM {n} ORDER BY ALL").fetchall() for n in stage_tables
    ] == stage_before
    for key in (
        "current_source_checked",
        "orphan_status_determined",
        "destructive_actions_authorized",
        "adoption_authorized",
        "retry_authorized",
        "recovery_execution_authorized",
        "publication_asserted",
        "decision_eligibility_asserted",
        "availability_evidence_verified",
        "historical_validity_asserted",
        "option_underlying_identity_binding_verified",
        "scenario_terms_authoritative",
        "model_suitability_verified",
        "source_acquisition_authenticity_asserted",
        "atomic_cross_database_snapshot_asserted",
    ):
        assert asdict(value)[key] is False
    assert value.canonical_contract_id is None and value.event_ts is None
    assert value.published_at is None


def test_wrong_reviewed_capture_fingerprint_stops_native(current_capture_case, monkeypatch):
    run = current_capture_case[0]

    def forbidden(*args, **kwargs):
        raise AssertionError("Unreviewed capture reached native work")

    monkeypatch.setattr(native, "plan_research_iv_stage_recovery", forbidden)
    value = run(expected_capture_fingerprint="0" * 64)
    assert value.status == "review_required"
    assert value.reason_codes == ("RECOVERY_CAPTURE_NOT_EXACT_REVIEWED_RECORDING",)
    assert value.fresh_before is None and not value.current_reconciliation_checked
    assert value.evidence_fingerprint is None and value.plan_evidence_fingerprint is None


def test_recorded_review_stops_even_when_later_inventory_is_good(
    capture_case,
    current_stage_case,
    monkeypatch,
):
    execute, capture, _, root = capture_case
    raw = b"synthetic unbound research artifact"
    path = root / (hashlib.sha256(raw).hexdigest() + ".research-iv.json")
    path.write_bytes(raw)
    recorded = execute()
    path.unlink()

    def forbidden(*args, **kwargs):
        raise AssertionError("Recorded review was upgraded")

    monkeypatch.setattr(native, "plan_research_iv_stage_recovery", forbidden)
    value = service.revalidate_research_iv_recovery_capture(
        current_stage_case[1],
        capture,
        capture_build_id_pin=recorded.build_id,
        expected_capture_fingerprint=recorded.evidence_fingerprint,
        artifact_root=root,
    )
    assert value.reason_codes == ("RECORDED_RECOVERY_REVIEW_CANNOT_BE_UPGRADED",)
    assert value.archived_recording_verified and not value.current_reconciliation_checked
    assert value.fresh_before is None and value.evidence_fingerprint is None


def test_changed_inventory_yields_review_not_recording_refresh(current_capture_case):
    run, _, _, root, _, _ = current_capture_case
    raw = b"synthetic new unbound artifact"
    path = root / (hashlib.sha256(raw).hexdigest() + ".research-iv.json")
    path.write_bytes(raw)
    value = run()
    assert value.status == "review_required" and value.current_reconciliation_checked
    assert value.fresh_before.status == value.fresh_after.status == "review_required"
    assert not value.exact_recorded_plan_reproduced
    assert value.capture_unchanged_observed
    assert value.plan_evidence_fingerprint is None and value.evidence_fingerprint is None
    assert path.read_bytes() == raw


@pytest.mark.parametrize("initial_bad", [False, True], ids=["good-bad", "bad-good"])
def test_both_actual_negative_orderings_retained(current_capture_case, monkeypatch, initial_bad):
    run, _, _, root, _, _ = current_capture_case
    raw = b"synthetic toggle artifact"
    path = root / (hashlib.sha256(raw).hexdigest() + ".research-iv.json")
    if initial_bad:
        path.write_bytes(raw)
    real = native.plan_research_iv_stage_recovery
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            if initial_bad:
                path.unlink()
            else:
                path.write_bytes(raw)
        return value

    monkeypatch.setattr(native, "plan_research_iv_stage_recovery", observe)
    value = run()
    assert calls == 2 and value.status == "review_required"
    assert value.fresh_before.status != value.fresh_after.status
    assert "CURRENT_RECOVERY_PLANS_DIFFER" in value.reason_codes
    assert not value.exact_recorded_plan_reproduced and value.evidence_fingerprint is None


def pending(capture):
    return AuditLedger(capture).plan_job(
        command_name=store.COMMAND,
        actor_id="synthetic",
        scope_ref="f" * 64,
        code_revision="synthetic",
        config_hash=store.sha(store.canonical(store.DEFINITION).encode()),
    )


def test_capture_audit_failure_before_stops_native(current_capture_case, monkeypatch):
    run, capture, _, _, _, _ = current_capture_case
    pending(capture)

    def forbidden(*args, **kwargs):
        raise AssertionError("Incomplete capture reached native work")

    monkeypatch.setattr(native, "plan_research_iv_stage_recovery", forbidden)
    value = run()
    assert value.reason_codes == ("RECOVERY_CAPTURE_ORIGINAL_RECORDING_INCOMPLETE_BEFORE",)
    assert value.fresh_before is None and value.evidence_fingerprint is None


def test_after_capture_audit_failure_preserves_both_native_plans(
    current_capture_case,
    monkeypatch,
):
    run, capture, _, _, _, _ = current_capture_case
    real = native.plan_research_iv_stage_recovery
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            pending(capture)
        return value

    monkeypatch.setattr(native, "plan_research_iv_stage_recovery", observe)
    value = run()
    assert calls == 2 and value.fresh_before is not None and value.fresh_after is not None
    assert value.status == "review_required"
    assert value.exact_recorded_plan_reproduced and not value.capture_unchanged_observed
    assert "RECOVERY_CAPTURE_ORIGINAL_RECORDING_INCOMPLETE_AFTER" in value.reason_codes
    assert value.evidence_fingerprint is None and value.plan_evidence_fingerprint is None


def test_capture_clock_change_blocks_positive_despite_exact_plans(
    current_capture_case,
    monkeypatch,
):
    run, capture, _, _, _, _ = current_capture_case
    real = native.plan_research_iv_stage_recovery
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            table = store._name(capture, "gold", store.TABLE)
            capture.execute(f"UPDATE {table} SET recorded_at=recorded_at+INTERVAL '1 second'")
        return value

    monkeypatch.setattr(native, "plan_research_iv_stage_recovery", observe)
    value = run()
    assert value.exact_recorded_plan_reproduced and not value.capture_unchanged_observed
    assert value.capture_before != value.capture_after
    assert value.reason_codes == ("RECOVERY_CAPTURE_RECORDING_OR_AUDIT_CHANGED",)
    assert value.evidence_fingerprint is None


def test_second_native_exception_never_returns_partial(current_capture_case, monkeypatch):
    run = current_capture_case[0]
    real = native.plan_research_iv_stage_recovery
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic second current plan failure")
        return real(*args, **kwargs)

    monkeypatch.setattr(native, "plan_research_iv_stage_recovery", observe)
    with pytest.raises(OSError, match="synthetic second current plan failure"):
        run()
    assert calls == 2


def test_readonly_capture_handle(current_capture_case):
    run, capture, _, _, path, _ = current_capture_case
    capture.close()
    with duckdb.connect(str(path), read_only=True) as connection:
        assert run(connection=connection).status == "matched_current_research_iv_recovery_capture"


def test_artifact_mutation_propagates_without_repair(current_capture_case):
    run, _, _, root, _, _ = current_capture_case
    files = list(root.iterdir())
    assert len(files) == 1
    files[0].write_bytes(b"synthetic invalid artifact")
    with pytest.raises(ValueError):
        run()
    assert files[0].read_bytes() == b"synthetic invalid artifact"


def test_same_live_capture_alias_rejected_parent_usable(current_capture_case):
    _, capture, recorded, root, _, _ = current_capture_case
    cursor = capture.cursor()
    assert cursor is not capture
    row = capture.execute("SELECT current_database()").fetchone()
    assert row is not None
    cursor.execute('USE "' + str(row[0]).replace('"', '""') + '"')
    try:
        with pytest.raises(ValueError, match="SEPARATE_DATABASE_REQUIRED"):
            service.revalidate_research_iv_recovery_capture(
                cursor,
                capture,
                capture_build_id_pin=recorded.build_id,
                expected_capture_fingerprint=recorded.evidence_fingerprint,
                artifact_root=root,
            )
        assert capture.execute("SELECT 1").fetchone() == (1,)
    finally:
        cursor.close()


def test_exact_recorded_root_not_replaceable(current_capture_case, tmp_path):
    run = current_capture_case[0]
    absent = tmp_path / "not-recorded-root"
    with pytest.raises(ValueError, match="EXACT_RECORDED_ROOT_REQUIRED"):
        run(artifact_root=absent)
    assert not absent.exists()


def test_no_frozen_stage_pin_refresh_on_changed_recording(current_capture_case):
    run, _, _, _, _, staging = current_capture_case
    from nse_quant.data_platform import research_iv_first_stage as stage

    table = stage._name(staging, "gold", stage.TABLES[1])
    staging.execute(f"UPDATE {table} SET recorded_at=recorded_at+INTERVAL '1 second'")
    # The actual native plan fails on the frozen stage fingerprint; never refresh it.
    with pytest.raises(ValueError, match="EXACT_REVIEWED_STAGE"):
        run()


def test_metadata_drift_is_not_hidden_by_unchanged_artifact_bytes(current_capture_case):
    run, _, _, root, _, _ = current_capture_case
    files = list(root.iterdir())
    assert len(files) == 1
    path = files[0]
    raw = path.read_bytes()
    info = path.stat()
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000000))
    value = run()
    assert value.fresh_before.status == value.fresh_after.status == "reconciled_retain_only"
    assert value.status == "review_required" and not value.exact_recorded_plan_reproduced
    assert value.capture_unchanged_observed and value.evidence_fingerprint is None
    assert path.read_bytes() == raw
