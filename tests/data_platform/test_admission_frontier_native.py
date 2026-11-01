"""Native integration with a substituted publication-reader boundary, not full E2E."""

import duckdb
import pytest

from nse_quant.data_platform import admission_capture as capture
from nse_quant.data_platform import admission_capture_reader as archive
from nse_quant.data_platform import admission_frontier as frontier
from nse_quant.data_platform import admission_frontier_revalidation as guard
from nse_quant.data_platform import publication_admission as policy
from nse_quant.data_platform.quote_publication_reader import ResearchPublicationEvidence


@pytest.fixture
def native_inputs(tmp_path, monkeypatch):
    path = tmp_path / "publications.duckdb"
    with duckdb.connect(str(path)) as conn:
        conn.execute("CREATE TABLE marker(id INTEGER)")
    publications = duckdb.connect(str(path), read_only=True)
    captures = duckdb.connect(str(tmp_path / "decision_inputs.duckdb"))
    value = ResearchPublicationEvidence(
        "research-quote-publication-consumer@1", "a" * 64, "blocked", "SOURCE_BLOCKED"
    )
    monkeypatch.setattr(policy, "read_research_publication", lambda *a, **k: value)
    request = policy.AdmissionRequest(policy.ARCHIVED_RESEARCH)

    def persist():
        return capture.capture_publication_admission(
            publications,
            captures,
            publication_id=value.publication_id,
            request=request,
            actor_id="test",
            code_revision="b175e2c",
            initialize=True,
        )

    first = persist()

    def run():
        return guard.revalidate_with_capture_frontier(
            publications,
            captures,
            receipt_id=first["receipt_id"],
            publication_id=value.publication_id,
            request=request,
        )

    yield captures, first, persist, run
    publications.close()
    captures.close()


def test_native_rejection_with_stable_frontier_is_not_authority(native_inputs):
    captures, _, _, run = native_inputs
    before = frontier.observe_admission_frontier(captures)
    result = run()
    assert result.status == "rejected"
    assert result.native_result.current_request_checked
    assert result.capture_frontier_unchanged_observed
    assert result.before.fingerprint == result.after.fingerprint
    assert not result.research_policy_satisfied
    assert not result.research_analysis_authorized
    assert not result.decision_eligibility_asserted
    assert not result.authenticity_asserted
    assert not result.atomic_cross_database_snapshot_asserted
    assert frontier.observe_admission_frontier(captures) == before


def test_exact_retry_changes_frontier_even_when_archive_dto_is_identical(native_inputs):
    captures, first, persist, _ = native_inputs
    before_dto = archive.read_admission_capture(captures, receipt_id=first["receipt_id"])
    before = frontier.observe_admission_frontier(captures)
    assert not persist()["inserted"]
    after_dto = archive.read_admission_capture(captures, receipt_id=first["receipt_id"])
    after = frontier.observe_admission_frontier(captures)
    assert before_dto == after_dto
    assert before.fingerprint != after.fingerprint


def test_successful_retry_during_native_assessment_requires_review(native_inputs, monkeypatch):
    _, _, persist, run = native_inputs
    original = policy.assess_publication_use
    calls = 0

    def assess(*args, **kwargs):
        nonlocal calls
        receipt = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            persist()
        return receipt

    monkeypatch.setattr(policy, "assess_publication_use", assess)
    result = run()
    assert result.native_result.status == "rejected"
    assert result.status == "review_required"
    assert result.reason_codes == ("CAPTURE_DATABASE_FRONTIER_CHANGED",)
    assert not result.capture_frontier_unchanged_observed
    assert not result.research_policy_satisfied


def test_unlinked_pending_job_is_included_without_success_filter(native_inputs):
    from nse_quant.data_platform.audit import AuditLedger

    captures, first, _, run = native_inputs
    before = frontier.observe_admission_frontier(captures)
    AuditLedger(captures).plan_job(
        command_name=capture.COMMAND,
        actor_id="test",
        code_revision="test",
        scope_ref="sha256:" + first["request_revision_id"],
        config_hash="untrusted",
    )
    after = frontier.observe_admission_frontier(captures)
    assert before.fingerprint != after.fingerprint
    result = run()
    assert result.status == "review_required"
    assert not result.research_policy_satisfied


def test_guard_coverage_limit_is_review_not_rejection(native_inputs, monkeypatch):
    _, _, _, run = native_inputs
    monkeypatch.setitem(frontier.LIMITS, ("decision_inputs", "admission_receipts"), 0)
    result = run()
    assert result.status == "review_required"
    assert result.native_result is None
    assert not result.capture_frontier_unchanged_observed
