"""Actual native revalidation/archive/model with existing lower source substitute.

Supplied for repository QA, NOT sandbox-executed and NOT full acquisition E2E.
"""

from dataclasses import replace

import pytest
from test_gold_quote_reader import setup as setup
from test_native_research_iv_bundle_boundary import bundle_case as bundle_case
from test_native_research_option_boundary import scenario as scenario
from test_research_iv_bundle_revalidation_boundary import (
    current_bundle_case as current_bundle_case,
)
from test_research_iv_bundle_store_boundary import writer as writer
from test_research_iv_revalidation_boundary import revalidation_case as revalidation_case
from test_research_iv_store_boundary import archive_case as archive_case

from nse_quant.data_platform import native_research_iv_artifact as materialization
from nse_quant.data_platform import research_iv_bundle_revalidation as current_service
from nse_quant.data_platform import research_iv_bundle_store as archive_store
from nse_quant.data_platform.research_iv_artifact_files import ResearchIvArtifactFiles
from nse_quant.data_platform.research_iv_bundle import encode_research_iv_bundle


@pytest.fixture
def artifact_case(current_bundle_case, tmp_path):
    target, _, run, receipt, reviewed, sources, gold, archive, _, _ = current_bundle_case
    observed = run()
    assert observed.status == "matched_current_research_iv_bundle"
    root = tmp_path / "research-artifacts"

    def execute(**changes):
        arguments = dict(
            build_id_pin=receipt["build_id"],
            expected_archive_fingerprint=reviewed.evidence_fingerprint,
            expected_bundle_id=observed.bundle_id,
            expected_revalidation_fingerprint=observed.evidence_fingerprint,
            artifact_root=root,
            initialize=True,
        )
        arguments.update(changes)
        return materialization.materialize_research_iv_artifact(
            *sources,
            gold,
            archive,
            target,
            **arguments,
        )

    return execute, root, observed, current_bundle_case


def test_materializes_exact_bytes_with_two_real_revalidations_and_no_db_writes(artifact_case):
    execute, root, observed, case = artifact_case
    target = case[0]
    tables = [archive_store._name(target, "gold", name) for name in archive_store.DOMAIN_TABLES]
    tables.extend(
        archive_store._name(target, "medallion_audit", name)
        for name in ("dataset_contracts", "jobs", "job_events")
    )
    before = [target.execute(f"SELECT * FROM {name} ORDER BY ALL").fetchall() for name in tables]
    value = execute()
    assert value.status == "materialized_research_iv_artifact_not_staged"
    assert value.before == value.after == observed
    assert value.artifact_written and value.artifact_bytes_rechecked
    assert value.audited_stage_recorded is False
    assert value.publication_asserted is False and value.decision_eligibility_asserted is False
    assert value.canonical_contract_id is None
    assert value.event_ts is None and value.published_at is None
    assert observed.fresh_before is not None and observed.fresh_before.bundle is not None
    raw = encode_research_iv_bundle(observed.fresh_before.bundle)
    assert ResearchIvArtifactFiles(root).read_exact(observed.bundle_id) == raw
    after = [target.execute(f"SELECT * FROM {name} ORDER BY ALL").fetchall() for name in tables]
    assert before == after


def test_existing_file_never_adopted_even_after_fresh_match(artifact_case):
    execute, root, observed, _ = artifact_case
    execute()
    path = ResearchIvArtifactFiles(root).path(observed.bundle_id)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        execute(initialize=False)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "field",
    ["expected_archive_fingerprint", "expected_revalidation_fingerprint", "expected_bundle_id"],
    ids=["archive", "revalidation", "bundle"],
)
def test_review_pin_mismatch_never_creates_root(artifact_case, field):
    execute, root, _, _ = artifact_case
    value = execute(**{field: "0" * 64})
    assert value.status == "review_required" and not value.artifact_written
    assert not root.exists()


def test_before_source_negative_prevents_file_creation(artifact_case):
    execute, root, _, case = artifact_case
    current, option = case[-2:]
    current[option.source_assessment_revision_id] = replace(option, status="blocked")
    value = execute()
    assert value.before.status == "review_required" and value.after is None
    assert not value.artifact_written and not root.exists()


def test_after_negative_kept_and_final_file_is_unbound_review_artifact(artifact_case, monkeypatch):
    execute, root, observed, case = artifact_case
    current, option = case[-2:]
    real = current_service.revalidate_research_iv_bundle
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            current[option.source_assessment_revision_id] = replace(option, status="blocked")
        return value

    monkeypatch.setattr(current_service, "revalidate_research_iv_bundle", observe)
    value = execute()
    assert calls == 2 and value.status == "review_required"
    assert value.before.status == "matched_current_research_iv_bundle"
    assert value.after.status == "review_required"
    assert value.artifact_written and value.artifact_bytes_rechecked
    assert not value.audited_stage_recorded
    assert ResearchIvArtifactFiles(root).read_exact(observed.bundle_id)


def test_second_native_exception_leaves_orphan_never_accepted(artifact_case, monkeypatch):
    execute, root, observed, _ = artifact_case
    real = current_service.revalidate_research_iv_bundle
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_AFTER_FILE_FAILURE")
        return real(*args, **kwargs)

    monkeypatch.setattr(current_service, "revalidate_research_iv_bundle", observe)
    with pytest.raises(RuntimeError, match="SYNTHETIC_AFTER_FILE_FAILURE"):
        execute()
    assert ResearchIvArtifactFiles(root).read_exact(observed.bundle_id)


def test_root_containing_database_rejected_before_native_work(artifact_case, monkeypatch):
    execute, root, _, _ = artifact_case

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid artifact root reached native revalidation")

    monkeypatch.setattr(current_service, "revalidate_research_iv_bundle", forbidden)
    with pytest.raises(ValueError, match="ROOT_MUST_BE_SEPARATE_FROM_DATABASES"):
        execute(artifact_root=root.parent)
    assert not root.exists()


def test_archive_retry_after_write_is_not_silent_reassessment(artifact_case, monkeypatch):
    execute, _, _, case = artifact_case
    persist = case[1]
    real = current_service.revalidate_research_iv_bundle
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            persist()
        return value

    monkeypatch.setattr(current_service, "revalidate_research_iv_bundle", observe)
    value = execute()
    assert calls == 2 and value.status == "review_required"
    assert value.artifact_written and not value.audited_stage_recorded
    assert value.after.reason_codes == ("IV_BUNDLE_PIN_NOT_REVIEWED_EXACT_ARCHIVED_HEAD",)
