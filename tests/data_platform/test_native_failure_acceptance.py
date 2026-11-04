"""Integrated actual-producer failure acceptance; no substituted lower-source boundary."""

from datetime import timedelta

import duckdb
import pytest
from native_failure_acceptance_lab import NativeFailureLab, table

from nse_quant.data_platform import admission_frontier as frontier
from nse_quant.data_platform import publication_admission as policy
from nse_quant.data_platform.audit import JobState


@pytest.fixture
def lab(tmp_path):
    return NativeFailureLab(tmp_path)


def assert_denials(value):
    assert value.decision_eligibility_asserted is False
    assert value.replay_authenticity_asserted is False


def test_actual_capture_revalidation_refuses_and_does_not_write(lab):
    before = lab.frontier()
    archived = lab.archived()
    assert archived.status == "verified_archived_capture"
    assert archived.pinned_receipt_is_history_head
    result = lab.revalidate()
    assert result.status == "rejected"
    assert result.archived_capture_verified and result.current_request_checked
    assert result.observed_inputs_match
    assert result.reason_codes == lab.original.reason_codes
    assert result.source_current_checked is False
    assert result.availability_evidence_verified is False
    assert result.economic_validity_verified is False
    assert result.atomic_cross_database_snapshot_asserted is False
    assert_denials(result)
    assert lab.frontier() == before


def test_request_axes_are_not_refreshed_to_make_a_capture_match(lab):
    for request in (
        policy.AdmissionRequest(policy.POINT_IN_TIME, lab.at + timedelta(seconds=1), lab.at),
        policy.AdmissionRequest(policy.POINT_IN_TIME, lab.at, lab.at + timedelta(seconds=1)),
        policy.AdmissionRequest(policy.ARCHIVED_RESEARCH),
    ):
        result = lab.revalidate(request)
        assert result.status == "review_required"
        assert result.reason_codes == ("CAPTURE_PUBLICATION_OR_REQUEST_PIN_MISMATCH",)
        assert not result.current_request_checked
        assert_denials(result)
    lab.replay()


def test_real_bronze_conflict_invalidates_gold_stage_not_archived_policy_replay(lab):
    before = lab.publication()
    assert before.status == "verified_research_snapshot"
    lab.append_frame_conflict()
    gold = lab.gold()
    assert gold.status == "blocked"
    assert gold.reason_code == "CURRENT_GOLD_SOURCE_EVIDENCE_CHANGED"
    stage = lab.stage()
    assert stage.status == "blocked"
    assert stage.reason_code == "STAGED_BUNDLE_SOURCE_REJECTED"
    assert stage.bundle is None
    assert not stage.decision_eligibility_asserted
    # Archived research publication verification is deliberately not a live source check.
    assert lab.publication() == before
    assert lab.revalidate().status == "rejected"
    assert lab.revalidate().source_current_checked is False
    lab.replay()


@pytest.mark.parametrize("damage", ["missing", "changed"], ids=["missing", "changed"])
def test_stage_artifact_damage_does_not_repair_or_destroy_retained_refusal(lab, damage):
    path = lab.artifacts / (lab.bundle_id + ".json")
    if damage == "missing":
        path.unlink()
        reason = "STAGED_ARTIFACT_MISSING_REVIEW_REQUIRED"
    else:
        path.write_bytes(b"corrupt-synthetic-artifact")
        reason = "STAGED_ARTIFACT_INVALID_REVIEW_REQUIRED"
    result = lab.stage()
    assert result.status == "blocked"
    assert result.reason_code == reason
    assert result.bundle is None
    assert path.exists() is (damage != "missing")
    assert lab.publication().status == "verified_research_snapshot"
    lab.replay()


def test_missing_capture_final_audit_is_not_healed_by_successful_retry(lab):
    with lab.opened("captures", writable=True) as (conn,):
        events = table(conn, "medallion_audit", "job_events")
        conn.execute(
            f"DELETE FROM {events} WHERE job_id=? AND state='SUCCEEDED'", [lab.capture["job_id"]]
        )
    retry = lab.retry()
    assert retry["inserted"] is False
    assert retry["receipt_id"] == lab.original.receipt_id
    assert retry["job_id"] != lab.capture["job_id"]
    archived = lab.archived()
    assert archived.archived_integrity_verified
    assert not archived.native_capture_provenance_verified
    assert not archived.reassessment_history_verified
    result = lab.revalidate()
    assert result.reason_codes == ("CAPTURE_NOT_VERIFIED_HISTORY_HEAD",)
    assert not result.current_request_checked
    lab.replay()


@pytest.mark.parametrize(
    "terminal",
    [None, JobState.FAILED, JobState.CANCELLED],
    ids=["running", "failed", "interrupted"],
)
def test_scoped_unlinked_obligation_survives_successful_retry(lab, terminal):
    before = lab.frontier()
    job = lab.add_scoped_job(terminal)
    assert lab.frontier().fingerprint != before.fingerprint
    retry = lab.retry()
    assert not retry["inserted"]
    archived = lab.archived()
    assert archived.archived_integrity_verified
    assert archived.native_capture_provenance_verified
    assert not archived.reassessment_history_verified
    assert archived.reason_codes == ("CAPTURE_ATTEMPT_COVERAGE_REVIEW_REQUIRED",)
    result = lab.revalidate()
    assert not result.current_request_checked
    assert result.status == "review_required"
    with lab.opened("captures") as (conn,):
        events = table(conn, "medallion_audit", "job_events")
        row = conn.execute(
            f"SELECT state FROM {events} WHERE job_id=? ORDER BY event_index DESC LIMIT 1", [job]
        ).fetchone()
        assert row == ("RUNNING" if terminal is None else terminal.value,)
    lab.replay()


def test_current_publication_drift_changes_complete_input_even_when_both_outcomes_reject(lab):
    with lab.opened("publications", writable=True) as (conn,):
        records = table(conn, "gold", "quote_bundle_publications")
        conn.execute(f"UPDATE {records} SET published_at=published_at + INTERVAL '1 second'")
    assert lab.publication().status == "verified_research_snapshot"
    result = lab.revalidate()
    assert result.status == "review_required"
    assert result.reason_codes == ("FRESH_INPUT_DIFFERS_FROM_CAPTURE_REASSESS_EXPLICITLY",)
    assert result.current_request_checked
    assert result.fresh_policy_status == "REJECTED"
    assert result.fresh_receipt_id != lab.original.receipt_id
    assert not result.observed_inputs_match
    assert_denials(result)
    lab.replay()


def test_missing_publication_final_audit_is_not_a_policy_only_match(lab):
    with lab.opened("publications", writable=True) as (conn,):
        events = table(conn, "medallion_audit", "job_events")
        conn.execute(f"DELETE FROM {events} WHERE state='SUCCEEDED'")
    publication = lab.publication()
    assert publication.status == "blocked"
    assert publication.reason_code == "PUBLICATION_ATTEMPT_NOT_TERMINAL"
    result = lab.revalidate()
    assert result.status == "review_required"
    assert result.fresh_policy_status == "REJECTED"
    assert not result.observed_inputs_match
    lab.replay()


@pytest.mark.parametrize(
    "field,expression",
    [
        ("status", "'ACCEPTED_DECISION'"),
        ("decision_eligibility_asserted", "True"),
        ("receipt_bytes", "'bad'::BLOB"),
        ("supersedes_json", "'[true]'"),
    ],
    ids=["status", "eligibility", "bytes", "links"],
)
def test_retained_database_tampering_never_uses_an_old_good_reader_cache(lab, field, expression):
    assert lab.archived().status == "verified_archived_capture"
    with lab.opened("captures", writable=True) as (conn,):
        records = table(conn, "decision_inputs", "admission_receipts")
        conn.execute(f'UPDATE {records} SET "{field}"={expression}')
    archived = lab.archived()
    assert archived.status == "review_required"
    assert not archived.reassessment_history_verified
    assert_denials(archived)
    assert lab.revalidate().current_request_checked is False
    # Retained pristine bytes replay locally but never repair the corrupted native DB.
    lab.replay()
    assert lab.archived().status == "review_required"


def test_actual_frontier_text_bound_no_limit_monkeypatch_or_salvage(lab):
    with lab.opened("captures", writable=True) as (conn,):
        jobs = table(conn, "medallion_audit", "jobs")
        conn.execute(f"UPDATE {jobs} SET actor_id=repeat('x', ?)", [frontier.MAX_TEXT_CELL + 1])
    with pytest.raises(
        frontier.FrontierReviewRequired, match="^FRONTIER_TEXT_BOUND_REVIEW_REQUIRED$"
    ):
        lab.frontier()
    lab.replay()


def test_frontier_rejects_unknown_objects_and_operational_failure_is_not_refusal(lab):
    with lab.opened("captures", writable=True) as (conn,):
        extra = table(conn, "decision_inputs", "unexpected")
        conn.execute(f"CREATE TABLE {extra} (id INTEGER)")
    with pytest.raises(
        frontier.FrontierReviewRequired, match="^FRONTIER_UNSUPPORTED_OBJECT_INVENTORY$"
    ):
        lab.frontier()
    assert lab.archived().status == "review_required"
    with lab.opened("publications", writable=True) as (conn,):
        records = table(conn, "gold", "quote_bundle_publications")
        conn.execute(f"DROP TABLE {records}")
    # Native SQL failures are operational exceptions, not manufactured policy decisions.
    with pytest.raises(duckdb.Error):
        lab.publication()
    lab.replay()


def test_actual_frontier_row_bound_is_not_hidden_by_success_filter(lab):
    with lab.opened("captures", writable=True) as (conn,):
        jobs = table(conn, "medallion_audit", "jobs")
        limit = frontier.LIMITS[("medallion_audit", "jobs")]
        conn.execute(
            f"INSERT INTO {jobs} SELECT j.job_id || '-overflow-' || cast(r.i AS VARCHAR),"
            "j.parent_job_id,j.command_name,j.actor_id,j.scope_ref,j.code_revision,"
            f"j.config_hash,j.created_at FROM {jobs} j CROSS JOIN range(?) r(i)",
            [limit],
        )
    with pytest.raises(
        frontier.FrontierReviewRequired, match="^FRONTIER_ROW_BOUND_REVIEW_REQUIRED$"
    ):
        lab.frontier()
    lab.replay()


def test_ambiguous_assessment_graph_blocks_before_good_payload_selection(lab):
    assert lab.gold().status == "verified_current"
    with lab.opened("assessments", writable=True) as (conn,):
        records = table(conn, "silver", "packet_reference_assessments")
        conn.execute(
            f"INSERT INTO {records} SELECT repeat('0',64),input_revision_id,"
            "source_observation_id,packet_ordinal,reference_assessment_revision_id,"
            "store_version,association_version,status,reason_code,association_fingerprint,"
            f"result_json,'[]',recorded_at,published_at,effective_from,effective_to,first_job_id "
            f"FROM {records}"
        )
    assert lab.gold().reason_code == "CURRENT_GOLD_SOURCE_EVIDENCE_CHANGED"
    assert lab.stage().reason_code == "STAGED_BUNDLE_SOURCE_REJECTED"
    lab.replay()


def test_real_capture_final_audit_exception_preserves_domain_and_failed_origin(lab, monkeypatch):
    from nse_quant.data_platform.admission_capture import capture_publication_admission
    from nse_quant.data_platform.admission_capture_reader import read_admission_capture
    from nse_quant.data_platform.audit import AuditLedger

    original_transition = AuditLedger.transition
    path = lab.paths["captures"].parent / "interrupted_capture.duckdb"
    with lab.opened("publications") as (publications,), duckdb.connect(str(path)) as target:

        def fail_final(self, job_id, state, reason_code=None):
            if self.conn is target and state == JobState.SUCCEEDED:
                raise OSError("SYNTHETIC_FINAL_AUDIT_UNAVAILABLE")
            return original_transition(self, job_id, state, reason_code)

        args = dict(
            publication_id=lab.publication_id,
            request=policy.AdmissionRequest(policy.POINT_IN_TIME, lab.at, lab.at),
            initialize=True,
            **lab.identity,
        )
        with monkeypatch.context() as patch:
            patch.setattr(AuditLedger, "transition", fail_final)
            with pytest.raises(OSError, match="^SYNTHETIC_FINAL_AUDIT_UNAVAILABLE$"):
                capture_publication_admission(publications, target, **args)
        records = table(target, "decision_inputs", "admission_receipts")
        row = target.execute(
            f"SELECT receipt_id,first_job_id,receipt_bytes FROM {records}"
        ).fetchone()
        assert row is not None
        assert row[0] == lab.original.receipt_id
        assert bytes(row[2]) == lab.raw
        retried = capture_publication_admission(publications, target, **args)
        assert retried["inserted"] is False
        assert retried["job_id"] != row[1]
        archived = read_admission_capture(target, receipt_id=row[0])
        assert archived.archived_integrity_verified
        assert not archived.native_capture_provenance_verified
        events = table(target, "medallion_audit", "job_events")
        assert target.execute(
            f"SELECT state FROM {events} WHERE job_id=? ORDER BY event_index DESC LIMIT 1", [row[1]]
        ).fetchone() == ("RUNNING",)
    # New read-only observation after every owner closed proves persistence, not just live state.
    with duckdb.connect(str(path), read_only=True) as reopened:
        assert not read_admission_capture(
            reopened,
            receipt_id=lab.original.receipt_id,
        ).native_capture_provenance_verified
