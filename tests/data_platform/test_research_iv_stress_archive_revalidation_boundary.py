"""Actual native stress/model/source/archive, existing lower source substitute unchanged.

Supplied for local repository QA; not sandbox-executed, not native acquisition E2E.
"""

from dataclasses import asdict, replace
from typing import Any

import duckdb
import pytest
from test_research_iv_stress_archive_boundary import archive_case as archive_case
from test_research_iv_stress_archive_boundary import archive_stress_case as archive_stress_case
from test_research_iv_stress_archive_boundary import artifact_case as artifact_case
from test_research_iv_stress_archive_boundary import bundle_case as bundle_case
from test_research_iv_stress_archive_boundary import current_bundle_case as current_bundle_case
from test_research_iv_stress_archive_boundary import current_stage_case as current_stage_case
from test_research_iv_stress_archive_boundary import revalidation_case as revalidation_case
from test_research_iv_stress_archive_boundary import scenario as scenario
from test_research_iv_stress_archive_boundary import setup as setup
from test_research_iv_stress_archive_boundary import stage_case as stage_case
from test_research_iv_stress_archive_boundary import stress_case as stress_case
from test_research_iv_stress_archive_boundary import writer as writer

from nse_quant.data_platform import native_research_iv_spot_stress as native
from nse_quant.data_platform import research_iv_stress_archive as store
from nse_quant.data_platform import research_iv_stress_archive_record as record
from nse_quant.data_platform import research_iv_stress_archive_revalidation as service
from nse_quant.data_platform.audit import AuditLedger


@pytest.fixture
def current_stress_case(archive_stress_case):
    execute, target, path, case = archive_stress_case
    recorded = execute()
    sources, gold, archive = case[5:8]

    def run(connection=None, **changes):
        args: dict[str, Any] = dict(
            stress_record_id_pin=recorded.build_id,
            expected_recording_fingerprint=recorded.evidence_fingerprint,
        )
        args.update(changes)
        return service.revalidate_research_iv_spot_stress_archive(
            *sources,
            gold,
            archive,
            target if connection is None else connection,
            **args,
        )

    return run, target, recorded, path, case


def test_actual_two_native_calls_match_full_record_without_writes(current_stress_case, monkeypatch):
    run, target, recorded, _, _ = current_stress_case
    real = native.build_native_research_iv_spot_stress
    calls: list[native.NativeResearchIvSpotStress] = []

    def observe(*args, **kwargs):
        value = real(*args, **kwargs)
        calls.append(value)
        return value

    monkeypatch.setattr(native, "build_native_research_iv_spot_stress", observe)
    fingerprint = store._snapshot(target)
    value = run()
    assert len(calls) == 2 and calls[0] == calls[1]
    assert value.status == "matched_current_research_iv_spot_stress_archive"
    assert value.archive_before == value.archive_after == recorded
    assert value.fresh_before == calls[0] and value.fresh_after == calls[1]
    assert value.comparison is not None and value.comparison.all_observations_match
    assert value.archived_recording_verified and value.current_source_checked
    assert value.model_computation_rechecked and value.exact_recording_reproduced
    assert value.archive_unchanged_observed and value.study == calls[0].study
    assert value.native_stress_fingerprint == calls[0].evidence_fingerprint
    assert value.evidence_fingerprint is not None
    assert record.canonical(record.decode(recorded.record_json)["result"]) == record.canonical(
        asdict(calls[0])
    )
    assert store._snapshot(target) == fingerprint
    for key in record.DENIALS:
        assert getattr(value, key) is False
    for key in record.NULLS:
        assert getattr(value, key) is None
    assert value.source_option_event_ts == calls[0].source_option_event_ts
    assert value.source_spot_event_ts == calls[0].source_spot_event_ts


def test_wrong_record_fingerprint_stops_before_native(current_stress_case, monkeypatch):
    run = current_stress_case[0]

    def forbidden(*args, **kwargs):
        raise AssertionError("Unreviewed stress archive reached native pricing")

    monkeypatch.setattr(native, "build_native_research_iv_spot_stress", forbidden)
    value = run(expected_recording_fingerprint="0" * 64)
    assert value.reason_codes == ("STRESS_NOT_EXACT_REVIEWED_RECORDING",)
    assert value.fresh_before is None and value.study is None
    assert value.evidence_fingerprint is None


def test_recorded_review_stops_before_later_good_native(archive_stress_case, monkeypatch):
    execute, target, _, case = archive_stress_case
    sources, gold, archive = case[5:8]
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    recorded = execute()
    state[option.source_assessment_revision_id] = option

    def forbidden(*args, **kwargs):
        raise AssertionError("Recorded review reached later-good native work")

    monkeypatch.setattr(native, "build_native_research_iv_spot_stress", forbidden)
    value = service.revalidate_research_iv_spot_stress_archive(
        *sources,
        gold,
        archive,
        target,
        stress_record_id_pin=recorded.build_id,
        expected_recording_fingerprint=recorded.evidence_fingerprint,
    )
    assert value.reason_codes == ("RECORDED_STRESS_REVIEW_CANNOT_BE_PROMOTED",)
    assert value.archived_recording_verified and not value.current_source_checked
    assert value.study is None and value.evidence_fingerprint is None


def test_changed_source_yields_two_retained_negatives(current_stress_case):
    run, _, _, _, case = current_stress_case
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    value = run()
    assert value.status == "review_required" and value.current_source_checked
    assert value.fresh_before.status == value.fresh_after.status == "review_required"
    assert not value.model_computation_rechecked and not value.exact_recording_reproduced
    assert value.archive_unchanged_observed and value.study is None
    assert value.native_stress_fingerprint is None and value.evidence_fingerprint is None


@pytest.mark.parametrize("initial_bad", [False, True], ids=["good-bad", "bad-good"])
def test_both_native_negative_orderings_retained(current_stress_case, monkeypatch, initial_bad):
    run, _, _, _, case = current_stress_case
    state, option = case[-2:]
    if initial_bad:
        state[option.source_assessment_revision_id] = replace(option, status="blocked")
    real = native.build_native_research_iv_spot_stress
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            state[option.source_assessment_revision_id] = (
                option if initial_bad else replace(option, status="blocked")
            )
        return value

    monkeypatch.setattr(native, "build_native_research_iv_spot_stress", observe)
    value = run()
    assert calls == 2 and value.status == "review_required"
    assert value.fresh_before.status != value.fresh_after.status
    assert "CURRENT_STRESS_OBSERVATIONS_DIFFER" in value.reason_codes
    assert value.study is None and value.evidence_fingerprint is None


def pending(target):
    return AuditLedger(target).plan_job(
        command_name=store.COMMAND,
        actor_id="synthetic",
        scope_ref="f" * 64,
        code_revision="synthetic",
        config_hash=record.sha(record.canonical(record.DEFINITION).encode()),
    )


def test_incomplete_original_audit_stops_native(current_stress_case, monkeypatch):
    run, target, _, _, _ = current_stress_case
    pending(target)

    def forbidden(*args, **kwargs):
        raise AssertionError("Incomplete original audit reached native stress")

    monkeypatch.setattr(native, "build_native_research_iv_spot_stress", forbidden)
    value = run()
    assert value.reason_codes == ("STRESS_ORIGINAL_RECORDING_INCOMPLETE_BEFORE",)
    assert value.fresh_before is None and value.study is None


def test_known_after_audit_failure_retains_both_actual_native_observations(
    current_stress_case,
    monkeypatch,
):
    run, target, _, _, _ = current_stress_case
    real = native.build_native_research_iv_spot_stress
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            pending(target)
        return value

    monkeypatch.setattr(native, "build_native_research_iv_spot_stress", observe)
    value = run()
    assert calls == 2 and value.fresh_before is not None and value.fresh_after is not None
    assert value.model_computation_rechecked and value.exact_recording_reproduced
    assert not value.archive_unchanged_observed and value.status == "review_required"
    assert value.study is None and value.native_stress_fingerprint is None
    assert value.evidence_fingerprint is None


def test_recording_clock_drift_blocks_complete_recomputed_stress(current_stress_case, monkeypatch):
    run, target, _, _, _ = current_stress_case
    real = native.build_native_research_iv_spot_stress
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            name = store._name(target, "gold", store.TABLE)
            target.execute(f"UPDATE {name} SET recorded_at=recorded_at+INTERVAL '1 second'")
        return value

    monkeypatch.setattr(native, "build_native_research_iv_spot_stress", observe)
    value = run()
    assert value.exact_recording_reproduced and not value.archive_unchanged_observed
    assert value.archive_before != value.archive_after
    assert value.reason_codes == ("STRESS_ARCHIVE_RECORDING_OR_AUDIT_CHANGED",)
    assert value.study is None and value.evidence_fingerprint is None


def test_second_native_exception_never_returns_partial(current_stress_case, monkeypatch):
    run = current_stress_case[0]
    real = native.build_native_research_iv_spot_stress
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic second native stress failure")
        return real(*args, **kwargs)

    monkeypatch.setattr(native, "build_native_research_iv_spot_stress", observe)
    with pytest.raises(OSError, match="synthetic second native stress failure"):
        run()
    assert calls == 2


def test_readonly_stress_archive_handle(current_stress_case):
    run, target, _, path, _ = current_stress_case
    target.close()
    with duckdb.connect(str(path), read_only=True) as readonly:
        assert run(connection=readonly).status == "matched_current_research_iv_spot_stress_archive"


def test_same_live_stress_file_alias_rejected_parent_usable(current_stress_case):
    _, target, recorded, _, case = current_stress_case
    sources, gold, archive = case[5:8]
    cursor = target.cursor()
    assert cursor is not target
    row = target.execute("SELECT current_database()").fetchone()
    assert row is not None
    cursor.execute('USE "' + str(row[0]).replace('"', '""') + '"')
    try:
        with pytest.raises(ValueError, match="SEPARATE_CURRENT_STRESS_ARCHIVE"):
            service.revalidate_research_iv_spot_stress_archive(
                cursor,
                *sources[1:],
                gold,
                archive,
                target,
                stress_record_id_pin=recorded.build_id,
                expected_recording_fingerprint=recorded.evidence_fingerprint,
            )
        assert target.execute("SELECT 1").fetchone() == (1,)
    finally:
        cursor.close()


def test_changed_underlying_archive_fingerprint_is_not_refreshed(current_stress_case):
    run, _, recorded, _, case = current_stress_case
    from nse_quant.data_platform import research_iv_store as iv_store

    requested = record.decode(recorded.record_json)["request"]
    source_archive = case[7]
    name = iv_store._name(source_archive, "gold", "research_iv_builds")
    source_archive.execute(
        f"UPDATE {name} SET recorded_at=recorded_at+INTERVAL '1 second' WHERE build_id=?",
        [requested["pins"][0]],
    )
    value = run()
    assert value.status == "review_required" and not value.exact_recording_reproduced
    assert value.fresh_before.status == value.fresh_after.status == "review_required"
    assert value.archive_before == value.archive_after == recorded
    assert value.study is None and value.native_stress_fingerprint is None
    assert record.decode(value.archive_after.record_json)["request"] == requested


def test_unknown_record_id_does_not_select_latest(current_stress_case, monkeypatch):
    run = current_stress_case[0]

    def forbidden(*args, **kwargs):
        raise AssertionError("Unknown archive ID reached native work")

    monkeypatch.setattr(native, "build_native_research_iv_spot_stress", forbidden)
    value = run(stress_record_id_pin="0" * 64)
    assert value.reason_codes == ("STRESS_ORIGINAL_RECORDING_INCOMPLETE_BEFORE",)
    assert value.archive_before is None and value.study is None
