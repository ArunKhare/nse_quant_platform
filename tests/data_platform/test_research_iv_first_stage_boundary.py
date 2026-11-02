"""Actual audit/domain/file/materializer boundary, lower source kernel substituted.

Supplied for local QA. Not sandbox-executed; not full native acquisition E2E.
"""

from dataclasses import replace

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
from test_research_iv_revalidation_boundary import revalidation_case as revalidation_case
from test_research_iv_store_boundary import archive_case as archive_case

from nse_quant.data_platform import research_iv_first_stage as store
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.research_iv_artifact_files import ResearchIvArtifactFiles


@pytest.fixture
def stage_case(artifact_case, tmp_path):
    materialize, root, observed, case = artifact_case
    target = duckdb.connect(str(tmp_path / "first_stage.duckdb"))
    bundle_archive, _, _, receipt, reviewed, sources, gold, archive, _, _ = case

    def execute(**changes):
        arguments = dict(
            build_id_pin=receipt["build_id"],
            expected_archive_fingerprint=reviewed.evidence_fingerprint,
            expected_bundle_id=observed.bundle_id,
            expected_revalidation_fingerprint=observed.evidence_fingerprint,
            artifact_root=root,
            actor_id="synthetic-test",
            code_revision="synthetic-test",
            initialize=True,
            initialize_artifacts=True,
        )
        arguments.update(changes)
        return store.stage_new_research_iv_artifact(
            *sources,
            gold,
            archive,
            bundle_archive,
            target,
            **arguments,
        )

    yield execute, target, root, observed, case, materialize
    target.close()


def test_actual_stage_binding_audit_and_artifact_record_reader(stage_case):
    execute, target, root, _, _, _ = stage_case
    receipt = execute()
    value = store.read_research_iv_first_stage(
        target, build_id_pin=receipt["build_id"], artifact_root=root
    )
    assert value.status == "verified_research_stage_recording"
    assert value.archived_stage_recording_verified and value.artifact_bytes_checked
    assert value.current_source_checked is False
    assert value.publication_asserted is False and value.decision_eligibility_asserted is False
    assert receipt["audited_stage_recorded"] is True
    events = store._name(target, "medallion_audit", "job_events")
    assert target.execute(f"SELECT state FROM {events} ORDER BY event_index").fetchall() == [
        ("PLANNED",),
        ("RUNNING",),
        ("SUCCEEDED",),
    ]
    before = value
    with pytest.raises(store.IvFirstStageReviewRequired, match="EXISTS_NO_RETRY"):
        execute(initialize=False, initialize_artifacts=False)
    assert (
        store.read_research_iv_first_stage(
            target, build_id_pin=receipt["build_id"], artifact_root=root
        )
        == before
    )


def test_original_materializer_file_is_not_adopted(stage_case):
    execute, target, root, observed, _, materialize = stage_case
    materialize()
    original = ResearchIvArtifactFiles(root).read_exact(observed.bundle_id)
    with pytest.raises(FileExistsError):
        execute(initialize_artifacts=False)
    assert ResearchIvArtifactFiles(root).read_exact(observed.bundle_id) == original
    assert target.execute(
        f"SELECT count(*) FROM {store._name(target, 'gold', store.TABLES[1])}"
    ).fetchone() == (0,)
    with pytest.raises(store.IvFirstStageReviewRequired):
        execute(initialize=False, initialize_artifacts=False)


def test_negative_native_result_audited_failed_no_later_healing(stage_case):
    execute, target, root, _, case, _ = stage_case
    current, option = case[-2:]
    current[option.source_assessment_revision_id] = replace(option, status="blocked")
    with pytest.raises(store.IvFirstStageNativeRejected) as error:
        execute()
    assert error.value.observation.before.status == "review_required"
    assert not root.exists()
    events = store._name(target, "medallion_audit", "job_events")
    assert target.execute(f"SELECT state FROM {events} ORDER BY event_index").fetchall() == [
        ("PLANNED",),
        ("RUNNING",),
        ("FAILED",),
    ]
    current[option.source_assessment_revision_id] = option
    with pytest.raises(store.IvFirstStageReviewRequired):
        execute(initialize=False)


def test_contract_and_binding_and_attempt_rollback_together_leaves_orphan(stage_case, monkeypatch):
    execute, target, root, observed, _, _ = stage_case
    real = AuditLedger.register_contract

    def fail_after_register(self, contract):
        real(self, contract)
        raise RuntimeError("SYNTHETIC_DOMAIN_FAILURE")

    monkeypatch.setattr(AuditLedger, "register_contract", fail_after_register)
    with pytest.raises(RuntimeError, match="SYNTHETIC_DOMAIN_FAILURE"):
        execute()
    for schema, name in (
        ("gold", store.TABLES[1]),
        ("gold", store.TABLES[2]),
        ("medallion_audit", "dataset_contracts"),
    ):
        row = target.execute(f"SELECT count(*) FROM {store._name(target, schema, name)}").fetchone()
        assert row == (0,)
    assert ResearchIvArtifactFiles(root).read_exact(observed.bundle_id)


def test_final_audit_failure_blocks_committed_binding_and_retry(stage_case, monkeypatch):
    execute, target, root, _, _, _ = stage_case
    real = AuditLedger.transition

    def fail_completion(self, job_id, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT_FAILURE")
        return real(self, job_id, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail_completion)
    with pytest.raises(RuntimeError, match="SYNTHETIC_FINAL_AUDIT_FAILURE"):
        execute()
    row = target.execute(
        f"SELECT build_id FROM {store._name(target, 'gold', store.TABLES[1])}"
    ).fetchone()
    assert row is not None
    with pytest.raises(store.IvFirstStageReviewRequired):
        store.read_research_iv_first_stage(target, build_id_pin=row[0], artifact_root=root)
    monkeypatch.setattr(AuditLedger, "transition", real)
    with pytest.raises(store.IvFirstStageReviewRequired):
        execute(initialize=False, initialize_artifacts=False)


def test_record_reader_does_not_claim_current_source_truth(stage_case):
    execute, target, root, _, case, _ = stage_case
    receipt = execute()
    current, option = case[-2:]
    current[option.source_assessment_revision_id] = replace(option, status="blocked")
    value = store.read_research_iv_first_stage(
        target, build_id_pin=receipt["build_id"], artifact_root=root
    )
    assert value.status == "verified_research_stage_recording"
    assert not value.current_source_checked and not value.decision_eligibility_asserted


def test_artifact_mutation_is_not_repaired(stage_case):
    execute, target, root, observed, _, _ = stage_case
    receipt = execute()
    path = ResearchIvArtifactFiles(root).path(observed.bundle_id)
    path.write_bytes(b"SYNTHETIC_MUTATION")
    with pytest.raises(ValueError):
        store.read_research_iv_first_stage(
            target,
            build_id_pin=receipt["build_id"],
            artifact_root=root,
        )
    assert path.read_bytes() == b"SYNTHETIC_MUTATION"


def test_unlinked_job_in_another_scope_invalidates_whole_stage_profile(stage_case):
    execute, target, root, _, _, _ = stage_case
    receipt = execute()
    AuditLedger(target).plan_job(
        command_name=store.COMMAND,
        actor_id="synthetic-test",
        code_revision="synthetic-test",
        scope_ref="f" * 64,
        config_hash=store.sha(store.canonical(store.DEFINITION).encode()),
    )
    with pytest.raises(store.IvFirstStageReviewRequired):
        store.read_research_iv_first_stage(
            target,
            build_id_pin=receipt["build_id"],
            artifact_root=root,
        )
