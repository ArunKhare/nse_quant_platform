"""Actual archive/audit/model/Gold SQL paths with prior lower source-kernel substitute.

These are boundary integration tests, NOT full native acquisition-to-analytics E2E.
"""

from dataclasses import replace

import duckdb
import pytest
from test_gold_quote_reader import setup as setup
from test_native_research_option_boundary import scenario as scenario
from test_research_iv_store_boundary import archive_case as archive_case

from nse_quant.data_platform import native_research_option as native
from nse_quant.data_platform import research_iv_revalidation as service
from nse_quant.data_platform import research_iv_store as store
from nse_quant.data_platform.audit import AuditLedger


@pytest.fixture
def revalidation_case(archive_case, setup):
    target, persist, current, option, _ = archive_case
    sources, gold, _, _, _, _ = setup
    receipt = persist()
    archive = store.read_research_iv_archive(target, build_id_pin=receipt["build_id"])
    arguments = dict(
        build_id_pin=receipt["build_id"], expected_archive_fingerprint=archive.evidence_fingerprint
    )

    def run(archive_connection=None, **changes):
        conn = target if archive_connection is None else archive_connection
        return service.revalidate_research_iv_build(
            *sources, gold, conn, **dict(arguments, **changes)
        )

    return target, persist, current, option, run, receipt, archive, sources, gold


def test_exact_archive_and_two_native_recomputations_without_writes(revalidation_case):
    target, _, _, _, run, _, archived, _, _ = revalidation_case
    attempts = store._name(target, "gold", "research_iv_attempts")
    before = target.execute(f"SELECT * FROM {attempts} ORDER BY job_id").fetchall()
    value = run()
    assert value.status == "matched_current_research_iv"
    assert value.archived_recording_verified
    assert value.current_source_checked
    assert value.exact_recording_reproduced
    assert value.archive_unchanged_observed
    assert value.archive_before == value.archive_after == archived
    assert value.comparison.all_observations_match
    assert value.fresh_before.source_option_event_ts is None
    assert value.fresh_before.source_spot_event_ts is None
    assert not value.publication_asserted
    assert not value.availability_evidence_verified
    assert not value.historical_validity_asserted
    assert not value.scenario_terms_authoritative
    assert not value.option_underlying_identity_binding_verified
    assert not value.decision_eligibility_asserted
    assert not value.atomic_cross_database_snapshot_asserted
    assert value.canonical_contract_id is None
    assert target.execute(f"SELECT * FROM {attempts} ORDER BY job_id").fetchall() == before


def test_changed_source_not_replaced_with_recorded_good(revalidation_case):
    _, _, current, option, run, _, _, _, _ = revalidation_case
    current[option.source_assessment_revision_id] = replace(option, status="blocked")
    value = run()
    assert value.current_source_checked
    assert not value.exact_recording_reproduced
    assert value.fresh_before.status == value.fresh_after.status == "review_required"
    assert "RESEARCH_IV_FRESH_NATIVE_RESULT_NOT_COMPLETE" in value.reason_codes


def test_old_success_pin_stops_before_source_after_negative_head(revalidation_case, monkeypatch):
    _, persist, current, option, run, _, _, _, _ = revalidation_case
    current[option.source_assessment_revision_id] = replace(option, status="blocked")
    persist()
    current[option.source_assessment_revision_id] = option

    def forbidden(*args, **kwargs):
        raise AssertionError("Superseded archive pin reached native pricing")

    monkeypatch.setattr(native, "build_native_research_iv_candidate", forbidden)
    value = run()
    assert not value.current_source_checked
    assert not value.exact_recording_reproduced
    assert value.fresh_before is None


def test_recorded_review_head_cannot_be_promoted(revalidation_case, monkeypatch):
    target, persist, current, option, run, _, _, _, _ = revalidation_case
    current[option.source_assessment_revision_id] = replace(option, status="blocked")
    blocked = persist()
    archived = store.read_research_iv_archive(target, build_id_pin=blocked["build_id"])
    current[option.source_assessment_revision_id] = option

    def forbidden(*args, **kwargs):
        raise AssertionError("Recorded review reached native promotion")

    monkeypatch.setattr(native, "build_native_research_iv_candidate", forbidden)
    value = run(
        build_id_pin=blocked["build_id"], expected_archive_fingerprint=archived.evidence_fingerprint
    )
    assert value.reason_codes == ("RECORDED_IV_REVIEW_RESULT_CANNOT_BE_PROMOTED",)
    assert not value.exact_recording_reproduced
    assert value.fresh_before is None


def test_exact_archive_retry_between_observations_blocks(revalidation_case, monkeypatch):
    _, persist, _, _, run, _, _, _, _ = revalidation_case
    real = native.build_native_research_iv_candidate
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            persist(initialize=False)
        return value

    monkeypatch.setattr(native, "build_native_research_iv_candidate", observe)
    value = run()
    assert value.comparison.all_observations_match
    assert "RESEARCH_IV_ARCHIVE_HEAD_OR_HISTORY_CHANGED" in value.reason_codes
    assert not value.exact_recording_reproduced


def test_first_good_later_bad_is_retained_not_selected_away(revalidation_case, monkeypatch):
    _, _, current, option, run, _, _, _, _ = revalidation_case
    real = native.build_native_research_iv_candidate
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            current[option.source_assessment_revision_id] = replace(option, status="blocked")
        return value

    monkeypatch.setattr(native, "build_native_research_iv_candidate", observe)
    value = run()
    assert value.comparison.recorded_matches_first
    assert not value.comparison.recorded_matches_second
    assert "CURRENT_IV_OBSERVATIONS_DIFFER" in value.reason_codes
    assert not value.exact_recording_reproduced


def pending(target, receipt):
    AuditLedger(target).plan_job(
        command_name=store.COMMAND,
        actor_id="test",
        code_revision="synthetic",
        scope_ref=receipt["input_id"],
        config_hash=store.sha(store._definition().encode()),
    )


def test_pending_archive_obligation_before_blocks(revalidation_case):
    target, _, _, _, run, receipt, _, _, _ = revalidation_case
    pending(target, receipt)
    value = run()
    assert value.reason_codes == ("RESEARCH_IV_ARCHIVE_OR_AUDIT_NOT_COMPLETE_BEFORE",)
    assert value.archive_before is None
    assert not value.current_source_checked


def test_pending_archive_obligation_after_keeps_native_observations(revalidation_case, monkeypatch):
    target, _, _, _, run, receipt, _, _, _ = revalidation_case
    real = native.build_native_research_iv_candidate
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            pending(target, receipt)
        return value

    monkeypatch.setattr(native, "build_native_research_iv_candidate", observe)
    value = run()
    assert value.reason_codes == ("RESEARCH_IV_ARCHIVE_OR_AUDIT_NOT_COMPLETE_AFTER",)
    assert value.fresh_before is not None and value.fresh_after is not None
    assert value.archive_after is None
    assert not value.exact_recording_reproduced


def test_reviewed_archive_fingerprint_required(revalidation_case):
    _, _, _, _, run, _, _, _, _ = revalidation_case
    value = run(expected_archive_fingerprint="0" * 64)
    assert not value.current_source_checked
    assert value.fresh_before is None


def test_readonly_archive_handle(revalidation_case, tmp_path):
    target, _, _, _, run, _, _, _, _ = revalidation_case
    target.close()
    with duckdb.connect(str(tmp_path / "research_iv.duckdb"), read_only=True) as conn:
        assert run(archive_connection=conn).exact_recording_reproduced


def test_native_failure_propagates_without_success(revalidation_case, monkeypatch):
    _, _, _, _, run, _, _, _, _ = revalidation_case

    def fail(*args, **kwargs):
        raise RuntimeError("SYNTHETIC_NATIVE_FAILURE")

    monkeypatch.setattr(native, "build_native_research_iv_candidate", fail)
    with pytest.raises(RuntimeError, match="SYNTHETIC_NATIVE_FAILURE"):
        run()


def test_archive_source_cursor_alias_rejected_and_parent_usable(revalidation_case):
    target, _, _, _, _, receipt, archived, sources, gold = revalidation_case
    cursor = target.cursor()
    assert cursor is not target
    catalog = target.execute("SELECT current_database()").fetchone()
    assert catalog is not None
    alias = '"' + catalog[0].replace('"', '""') + '"'
    cursor.execute(f"USE {alias}")
    try:
        with pytest.raises(ValueError, match="SEPARATE_RESEARCH_IV_REVALIDATION_ARCHIVE"):
            service.revalidate_research_iv_build(
                cursor,
                *sources[1:],
                gold,
                target,
                build_id_pin=receipt["build_id"],
                expected_archive_fingerprint=archived.evidence_fingerprint,
            )
        assert target.execute("SELECT 1").fetchone() == (1,)
    finally:
        cursor.close()
