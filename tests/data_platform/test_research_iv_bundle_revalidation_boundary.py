"""Repository boundary integration; real assembly/audit/Gold, lower source substitute.

Not full native acquisition-to-revalidation E2E. Supplied, not sandbox-executed.
"""

from dataclasses import asdict, replace

import pytest
from test_gold_quote_reader import setup as setup
from test_native_research_iv_bundle_boundary import bundle_case as bundle_case
from test_native_research_option_boundary import scenario as scenario
from test_research_iv_bundle_store_boundary import writer as writer
from test_research_iv_revalidation_boundary import revalidation_case as revalidation_case
from test_research_iv_store_boundary import archive_case as archive_case

from nse_quant.data_platform import native_research_iv_bundle as native
from nse_quant.data_platform import research_iv_bundle_revalidation as service
from nse_quant.data_platform import research_iv_bundle_store as store
from nse_quant.data_platform.audit import AuditLedger


@pytest.fixture
def current_bundle_case(writer, bundle_case):
    target, _, persist, sources, gold, archive = writer
    _, _, _, _, current, option = bundle_case
    receipt = persist(initialize=True)
    reviewed = store.read_research_iv_bundle_archive(target, build_id_pin=receipt["build_id"])

    def run(connection=None, **changes):
        return service.revalidate_research_iv_bundle(
            *sources,
            gold,
            archive,
            target if connection is None else connection,
            **dict(
                dict(
                    build_id_pin=receipt["build_id"],
                    expected_archive_fingerprint=reviewed.evidence_fingerprint,
                ),
                **changes,
            ),
        )

    return target, persist, run, receipt, reviewed, sources, gold, archive, current, option


def pending(target, receipt):
    return AuditLedger(target).plan_job(
        command_name=store.COMMAND,
        actor_id="synthetic-test",
        code_revision="synthetic-test",
        scope_ref=receipt["input_id"],
        config_hash=store.sha(store._definition().encode()),
    )


def test_two_actual_whole_set_assemblies_reproduce_complete_recording(
    current_bundle_case,
    monkeypatch,
):
    target, _, run, _, reviewed, _, _, archive, _, _ = current_bundle_case
    snapshots = []
    for conn, tables in ((target, store.DOMAIN_TABLES[1:]), (archive, ("research_iv_attempts",))):
        for table in tables:
            snapshots.append((conn, store._name(conn, "gold", table)))
    for conn in (target, archive):
        for table in ("jobs", "job_events"):
            snapshots.append((conn, store._name(conn, "medallion_audit", table)))
    before = [
        conn.execute(f"SELECT * FROM {name} ORDER BY ALL").fetchall() for conn, name in snapshots
    ]
    real = native.assemble_native_research_iv_bundle
    calls = []

    def observe(*args, **kwargs):
        value = real(*args, **kwargs)
        calls.append(value)
        return value

    monkeypatch.setattr(native, "assemble_native_research_iv_bundle", observe)
    value = run()
    assert len(calls) == 2
    assert value.status == "matched_current_research_iv_bundle"
    assert value.archive_before == value.archive_after == reviewed
    assert value.fresh_before == calls[0] and value.fresh_after == calls[1]
    assert value.comparison is not None and value.comparison.all_observations_match
    assert value.exact_recording_reproduced and value.all_members_revalidated
    assert value.archived_recording_verified and value.current_source_checked
    assert value.archive_unchanged_observed
    assert value.fresh_before.bundle is not None
    assert value.bundle_id == value.fresh_before.bundle.bundle_id
    assert all(
        member.source_option_event_ts is None for member in value.fresh_before.bundle.members
    )
    for key in (
        "publication_asserted",
        "availability_evidence_verified",
        "historical_validity_asserted",
        "option_underlying_identity_binding_verified",
        "scenario_terms_authoritative",
        "model_suitability_verified",
        "source_acquisition_authenticity_asserted",
        "atomic_cross_database_snapshot_asserted",
        "decision_eligibility_asserted",
    ):
        assert asdict(value)[key] is False
    assert value.canonical_contract_id is None
    after = [
        conn.execute(f"SELECT * FROM {name} ORDER BY ALL").fetchall() for conn, name in snapshots
    ]
    assert before == after


def test_wrong_review_fingerprint_stops_before_assembly(current_bundle_case, monkeypatch):
    _, _, run, _, _, _, _, _, _, _ = current_bundle_case

    def forbidden(*args, **kwargs):
        raise AssertionError("Wrong reviewed fingerprint reached assembly")

    monkeypatch.setattr(native, "assemble_native_research_iv_bundle", forbidden)
    value = run(expected_archive_fingerprint="0" * 64)
    assert value.reason_codes == ("IV_BUNDLE_PIN_NOT_REVIEWED_EXACT_ARCHIVED_HEAD",)
    assert not value.current_source_checked and value.fresh_before is None


def test_superseded_good_and_recorded_review_both_stop_before_assembly(
    current_bundle_case,
    monkeypatch,
):
    target, persist, run, _, _, _, _, _, current, option = current_bundle_case
    current[option.source_assessment_revision_id] = replace(option, status="blocked")
    bad = persist()
    reviewed = store.read_research_iv_bundle_archive(target, build_id_pin=bad["build_id"])
    current[option.source_assessment_revision_id] = option

    def forbidden(*args, **kwargs):
        raise AssertionError("Old or review recording reached native promotion")

    monkeypatch.setattr(native, "assemble_native_research_iv_bundle", forbidden)
    old = run()
    assert not old.current_source_checked and old.fresh_before is None
    value = run(
        build_id_pin=bad["build_id"], expected_archive_fingerprint=reviewed.evidence_fingerprint
    )
    assert value.reason_codes == ("RECORDED_IV_BUNDLE_REVIEW_CANNOT_BE_PROMOTED",)
    assert value.archived_recording_verified
    assert not value.current_source_checked and value.fresh_before is None


def test_source_change_blocks_without_old_good_fallback(current_bundle_case):
    _, _, run, _, _, _, _, _, current, option = current_bundle_case
    current[option.source_assessment_revision_id] = replace(option, status="blocked")
    value = run()
    assert value.current_source_checked
    assert value.fresh_before.status == value.fresh_after.status == "review_required"
    assert not value.exact_recording_reproduced and value.bundle_id is None
    assert "IV_BUNDLE_FRESH_NATIVE_ASSEMBLY_NOT_COMPLETE" in value.reason_codes


@pytest.mark.parametrize("initial_bad", [False, True], ids=["good-then-bad", "bad-then-good"])
def test_both_negative_orderings_are_retained(current_bundle_case, monkeypatch, initial_bad):
    _, _, run, _, _, _, _, _, current, option = current_bundle_case
    if initial_bad:
        current[option.source_assessment_revision_id] = replace(option, status="blocked")
    real = native.assemble_native_research_iv_bundle
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            current[option.source_assessment_revision_id] = (
                option if initial_bad else replace(option, status="blocked")
            )
        return value

    monkeypatch.setattr(native, "assemble_native_research_iv_bundle", observe)
    value = run()
    assert calls == 2
    assert value.fresh_before.status != value.fresh_after.status
    assert value.bundle_id is None and not value.exact_recording_reproduced
    assert "CURRENT_IV_BUNDLE_OBSERVATIONS_DIFFER" in value.reason_codes


def test_exact_bundle_archive_retry_between_assemblies_invalidates_history(
    current_bundle_case,
    monkeypatch,
):
    _, persist, run, _, _, _, _, _, _, _ = current_bundle_case
    real = native.assemble_native_research_iv_bundle
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            # Avoid recursively re-entering this observation hook for the test write.
            monkeypatch.setattr(native, "assemble_native_research_iv_bundle", real)
            try:
                persist()
            finally:
                monkeypatch.setattr(native, "assemble_native_research_iv_bundle", observe)
        return value

    monkeypatch.setattr(native, "assemble_native_research_iv_bundle", observe)
    value = run()
    assert calls == 2 and value.comparison.all_observations_match
    assert "IV_BUNDLE_ARCHIVE_HEAD_OR_HISTORY_CHANGED" in value.reason_codes
    assert not value.exact_recording_reproduced and value.bundle_id is None


def test_pending_origin_obligation_before_blocks(current_bundle_case, monkeypatch):
    target, _, run, receipt, _, _, _, _, _, _ = current_bundle_case
    pending(target, receipt)

    def forbidden(*args, **kwargs):
        raise AssertionError("Pending archive reached assembly")

    monkeypatch.setattr(native, "assemble_native_research_iv_bundle", forbidden)
    value = run()
    assert value.reason_codes == ("IV_BUNDLE_ARCHIVE_OR_AUDIT_NOT_COMPLETE_BEFORE",)
    assert value.fresh_before is None and not value.current_source_checked


def test_pending_obligation_after_retains_both_native_observations(
    current_bundle_case,
    monkeypatch,
):
    target, _, run, receipt, _, _, _, _, _, _ = current_bundle_case
    real = native.assemble_native_research_iv_bundle
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            pending(target, receipt)
        return value

    monkeypatch.setattr(native, "assemble_native_research_iv_bundle", observe)
    value = run()
    assert calls == 2
    assert value.fresh_before is not None and value.fresh_after is not None
    assert value.archive_after is None and not value.exact_recording_reproduced
    assert "IV_BUNDLE_ARCHIVE_OR_AUDIT_NOT_COMPLETE_AFTER" in value.reason_codes


def test_native_exception_cannot_return_partial_success(current_bundle_case, monkeypatch):
    _, _, run, _, _, _, _, _, _, _ = current_bundle_case
    real = native.assemble_native_research_iv_bundle
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_ASSEMBLY_FAILURE")
        return real(*args, **kwargs)

    monkeypatch.setattr(native, "assemble_native_research_iv_bundle", observe)
    with pytest.raises(RuntimeError, match="SYNTHETIC_SECOND_ASSEMBLY_FAILURE"):
        run()
    assert calls == 2


def test_readonly_bundle_archive_handle(current_bundle_case, tmp_path):
    import duckdb

    target, _, run, _, _, _, _, _, _, _ = current_bundle_case
    target.close()
    with duckdb.connect(str(tmp_path / "bundle-output.duckdb"), read_only=True) as conn:
        assert run(connection=conn).exact_recording_reproduced


def test_distinct_cursor_same_file_is_rejected_parent_remains_usable(current_bundle_case):
    target, _, _, receipt, reviewed, sources, gold, _, _, _ = current_bundle_case
    cursor = target.cursor()
    assert cursor is not target
    catalog = target.execute("SELECT current_database()").fetchone()
    assert catalog is not None
    cursor.execute('USE "' + str(catalog[0]).replace('"', '""') + '"')
    try:
        with pytest.raises(ValueError, match="SEPARATE_IV_BUNDLE_REVALIDATION_ARCHIVE"):
            service.revalidate_research_iv_bundle(
                *sources,
                gold,
                cursor,
                target,
                build_id_pin=receipt["build_id"],
                expected_archive_fingerprint=reviewed.evidence_fingerprint,
            )
        assert target.execute("SELECT 1").fetchone() == (1,)
    finally:
        cursor.close()


def test_member_archive_retry_does_not_refresh_frozen_review_pins(
    current_bundle_case,
    revalidation_case,
):
    _, _, run, _, reviewed, _, _, _, _, _ = current_bundle_case
    member_persist = revalidation_case[1]
    member_persist(initialize=False)
    value = run()
    assert value.archive_before.requests_json == reviewed.requests_json
    assert value.archive_unchanged_observed
    assert not value.exact_recording_reproduced and value.bundle_id is None
    assert value.fresh_before.status == value.fresh_after.status == "review_required"


def test_native_resource_bound_cannot_return_accepted_output(current_bundle_case, monkeypatch):
    _, _, run, _, _, _, _, _, _, _ = current_bundle_case
    monkeypatch.setattr(native, "MAX_PASS_BYTES", 1)
    with pytest.raises(ValueError, match="PASS_BYTE_LIMIT"):
        run()
