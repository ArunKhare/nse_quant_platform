"""Actual current-stage service/audit/artifact/model, existing lower source substitute.

Supplied for repository QA, NOT sandbox-executed and NOT full native acquisition E2E.
"""

from dataclasses import asdict, replace

import duckdb
import pytest
from test_gold_quote_reader import setup as setup
from test_native_research_iv_artifact_boundary import artifact_case as artifact_case
from test_native_research_iv_bundle_boundary import bundle_case as bundle_case
from test_native_research_option_boundary import scenario as scenario
from test_research_iv_bundle_revalidation_boundary import (
    current_bundle_case as current_bundle_case,
)
from test_research_iv_bundle_store_boundary import writer as writer
from test_research_iv_first_stage_boundary import stage_case as stage_case
from test_research_iv_revalidation_boundary import revalidation_case as revalidation_case
from test_research_iv_store_boundary import archive_case as archive_case

from nse_quant.data_platform import research_iv_bundle_revalidation as current
from nse_quant.data_platform import research_iv_first_stage as store
from nse_quant.data_platform import research_iv_stage_revalidation as service
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.research_iv_artifact_files import ResearchIvArtifactFiles


@pytest.fixture
def current_stage_case(stage_case):
    execute, staging, root, _, case, _ = stage_case
    receipt = execute()
    reviewed = store.read_research_iv_first_stage(
        staging,
        build_id_pin=receipt["build_id"],
        artifact_root=root,
    )
    bundle_archive, _, _, _, _, sources, gold, archive, _, _ = case

    def run(connection=None, **changes):
        arguments = dict(
            stage_build_id_pin=receipt["build_id"],
            expected_stage_fingerprint=reviewed.evidence_fingerprint,
            artifact_root=root,
        )
        arguments.update(changes)
        return service.revalidate_research_iv_first_stage(
            *sources,
            gold,
            archive,
            bundle_archive,
            staging if connection is None else connection,
            **arguments,
        )

    return run, staging, receipt, reviewed, root, case


def pending(staging):
    return AuditLedger(staging).plan_job(
        command_name=store.COMMAND,
        actor_id="synthetic-test",
        code_revision="synthetic-test",
        scope_ref="f" * 64,
        config_hash=store.sha(store.canonical(store.DEFINITION).encode()),
    )


def test_actual_current_stage_matches_frozen_dto_digests_and_bytes_without_writes(
    current_stage_case,
    monkeypatch,
):
    run, staging, _, reviewed, _, _ = current_stage_case
    names = [store._name(staging, "gold", name) for name in store.TABLES]
    names.extend(
        store._name(staging, "medallion_audit", name)
        for name in ("dataset_contracts", "jobs", "job_events")
    )
    before = [staging.execute(f"SELECT * FROM {name} ORDER BY ALL").fetchall() for name in names]
    real = current.revalidate_research_iv_bundle
    calls: list[current.ResearchIvBundleRevalidation] = []

    def observe(*args, **kwargs):
        value = real(*args, **kwargs)
        calls.append(value)
        return value

    monkeypatch.setattr(current, "revalidate_research_iv_bundle", observe)
    value = run()
    assert len(calls) == 2
    assert value.status == "matched_current_research_iv_stage"
    assert value.stage_before == value.stage_after == reviewed
    assert value.fresh_before == calls[0] and value.fresh_after == calls[1]
    assert value.comparison is not None and value.comparison.all_observations_match
    assert value.archived_stage_recording_verified and value.current_source_checked
    assert value.recorded_native_digests_matched and value.artifact_bytes_matched
    assert value.stage_unchanged_observed
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
    assert value.event_ts is None and value.published_at is None
    after = [staging.execute(f"SELECT * FROM {name} ORDER BY ALL").fetchall() for name in names]
    assert before == after


def test_wrong_reviewed_stage_fingerprint_stops_before_current_source(
    current_stage_case,
    monkeypatch,
):
    run, _, _, _, _, _ = current_stage_case

    def forbidden(*args, **kwargs):
        raise AssertionError("Unreviewed stage reached native source")

    monkeypatch.setattr(current, "revalidate_research_iv_bundle", forbidden)
    value = run(expected_stage_fingerprint="0" * 64)
    assert value.reason_codes == ("IV_STAGE_NOT_EXACT_REVIEWED_RECORDING",)
    assert value.fresh_before is None and not value.current_source_checked


def test_pending_stage_origin_obligation_blocks_before_native(current_stage_case, monkeypatch):
    run, staging, _, _, _, _ = current_stage_case
    pending(staging)

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid stage audit reached native source")

    monkeypatch.setattr(current, "revalidate_research_iv_bundle", forbidden)
    value = run()
    assert value.reason_codes == ("IV_STAGE_ORIGINAL_RECORDING_NOT_COMPLETE_BEFORE",)
    assert not value.current_source_checked


def test_changed_source_not_hidden_by_still_valid_original_stage_record(current_stage_case):
    run, _, _, _, _, case = current_stage_case
    state, option = case[-2:]
    state[option.source_assessment_revision_id] = replace(option, status="blocked")
    value = run()
    assert value.current_source_checked and value.stage_unchanged_observed
    assert value.fresh_before.status == value.fresh_after.status == "review_required"
    assert value.status == "review_required" and not value.recorded_native_digests_matched
    assert value.bundle_id is None and value.evidence_fingerprint is None


@pytest.mark.parametrize("initial_bad", [False, True], ids=["good-bad", "bad-good"])
def test_both_native_negative_orderings_retained(current_stage_case, monkeypatch, initial_bad):
    run, _, _, _, _, case = current_stage_case
    state, option = case[-2:]
    if initial_bad:
        state[option.source_assessment_revision_id] = replace(option, status="blocked")
    real = current.revalidate_research_iv_bundle
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

    monkeypatch.setattr(current, "revalidate_research_iv_bundle", observe)
    value = run()
    assert calls == 2 and value.status == "review_required"
    assert value.fresh_before.status != value.fresh_after.status
    assert not value.recorded_native_digests_matched and value.bundle_id is None
    assert "CURRENT_IV_STAGE_NATIVE_OBSERVATIONS_DIFFER" in value.reason_codes


def test_after_stage_audit_failure_keeps_both_actual_native_observations(
    current_stage_case,
    monkeypatch,
):
    run, staging, _, _, _, _ = current_stage_case
    real = current.revalidate_research_iv_bundle
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            pending(staging)
        return value

    monkeypatch.setattr(current, "revalidate_research_iv_bundle", observe)
    value = run()
    assert calls == 2 and value.status == "review_required"
    assert value.fresh_before is not None and value.fresh_after is not None
    assert value.comparison.all_observations_match
    assert value.stage_after is None and not value.stage_unchanged_observed
    assert "IV_STAGE_ORIGINAL_RECORDING_NOT_COMPLETE_AFTER" in value.reason_codes


def test_bundle_archive_retry_never_refreshes_frozen_review_pins(current_stage_case):
    run, _, _, _, _, case = current_stage_case
    case[1]()
    value = run()
    assert value.current_source_checked and value.status == "review_required"
    assert value.stage_unchanged_observed and not value.recorded_native_digests_matched
    assert value.bundle_id is None


def test_artifact_mutation_before_current_consumption_is_not_repaired(current_stage_case):
    run, _, _, reviewed, root, _ = current_stage_case
    body = store.decode(reviewed.record_json)
    path = ResearchIvArtifactFiles(root).path(body["pins"][2])
    path.write_bytes(b"SYNTHETIC_CHANGED_ARTIFACT")
    with pytest.raises(ValueError):
        run()
    assert path.read_bytes() == b"SYNTHETIC_CHANGED_ARTIFACT"


def test_second_native_exception_never_returns_partial_acceptance(current_stage_case, monkeypatch):
    run, _, _, _, _, _ = current_stage_case
    real = current.revalidate_research_iv_bundle
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_CURRENT_FAILURE")
        return real(*args, **kwargs)

    monkeypatch.setattr(current, "revalidate_research_iv_bundle", observe)
    with pytest.raises(RuntimeError, match="SYNTHETIC_SECOND_CURRENT_FAILURE"):
        run()
    assert calls == 2


def test_readonly_staging_handle(current_stage_case, tmp_path):
    run, staging, _, _, _, _ = current_stage_case
    staging.close()
    with duckdb.connect(str(tmp_path / "first_stage.duckdb"), read_only=True) as conn:
        assert run(connection=conn).status == "matched_current_research_iv_stage"


def test_distinct_cursor_same_live_stage_file_rejected_parent_usable(current_stage_case):
    _, staging, receipt, reviewed, root, case = current_stage_case
    bundle_archive, _, _, _, _, sources, gold, archive, _, _ = case
    cursor = staging.cursor()
    assert cursor is not staging
    row = staging.execute("SELECT current_database()").fetchone()
    assert row is not None
    cursor.execute('USE "' + str(row[0]).replace('"', '""') + '"')
    try:
        with pytest.raises(ValueError, match="SEPARATE_CURRENT_IV_STAGE_DATABASE"):
            service.revalidate_research_iv_first_stage(
                cursor,
                *sources[1:],
                gold,
                archive,
                bundle_archive,
                staging,
                stage_build_id_pin=receipt["build_id"],
                expected_stage_fingerprint=reviewed.evidence_fingerprint,
                artifact_root=root,
            )
        assert staging.execute("SELECT 1").fetchone() == (1,)
    finally:
        cursor.close()


def test_observation_byte_limit_cannot_return_accepted_prefix(current_stage_case, monkeypatch):
    run, _, _, _, _, _ = current_stage_case
    monkeypatch.setattr(service, "MAX_NATIVE_BYTES", 1)
    with pytest.raises(ValueError, match="NATIVE_OBSERVATION_BYTE_LIMIT"):
        run()


def test_artifact_change_after_native_calls_cannot_return_accepted_output(
    current_stage_case,
    monkeypatch,
):
    run, _, _, reviewed, root, _ = current_stage_case
    path = ResearchIvArtifactFiles(root).path(store.decode(reviewed.record_json)["pins"][2])
    real = current.revalidate_research_iv_bundle
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 2:
            path.write_bytes(b"SYNTHETIC_AFTER_NATIVE_MUTATION")
        return value

    monkeypatch.setattr(current, "revalidate_research_iv_bundle", observe)
    with pytest.raises(ValueError):
        run()
    assert calls == 2 and path.read_bytes() == b"SYNTHETIC_AFTER_NATIVE_MUTATION"


def test_changed_valid_stage_metadata_blocks_despite_matching_native_digests(
    current_stage_case,
    monkeypatch,
):
    run, staging, _, _, _, _ = current_stage_case
    real = current.revalidate_research_iv_bundle
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            table = store._name(staging, "gold", store.TABLES[1])
            staging.execute(f"UPDATE {table} SET recorded_at=recorded_at+INTERVAL '1 second'")
        return value

    monkeypatch.setattr(current, "revalidate_research_iv_bundle", observe)
    value = run()
    assert calls == 2 and value.comparison.all_observations_match
    assert value.stage_after is not None and value.stage_after != value.stage_before
    assert value.status == "review_required" and not value.stage_unchanged_observed
    assert "IV_STAGE_RECORDING_AUDIT_OR_ARTIFACT_CHANGED" in value.reason_codes
    assert value.bundle_id is None and value.evidence_fingerprint is None
