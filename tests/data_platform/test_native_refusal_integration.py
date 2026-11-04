"""Actual native producer/admission/audit integration; no successful computations replaced."""

import hashlib
from datetime import UTC, datetime

import duckdb
import pytest
from native_failure_acceptance_lab import NativeFailureLab, table

from nse_quant.data_platform import native_refusal_decision as kernel
from nse_quant.data_platform import native_refusal_store as store
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.native_refusal_service import evaluate_native_refusal


@pytest.fixture
def case(tmp_path):
    lab = NativeFailureLab(tmp_path)
    pub = lab.publication()
    assert pub.evidence_fingerprint is not None
    request = kernel.RefusalRequest(
        "synthetic-attempt",
        lab.publication_id,
        pub.evidence_fingerprint,
        lab.at,
        lab.at,
        "c" * 40,
        kill_switch="INACTIVE",
    )
    return lab, request, tmp_path / "native_decisions.duckdb"


def record(case):
    lab, request, path = case
    with lab.opened("publications") as (publications,), duckdb.connect(str(path)) as target:
        return store.record_native_refusal(
            publications,
            target,
            request=request,
            actor_id="synthetic",
            initialize=True,
        )


def read(case, receipt):
    with duckdb.connect(str(case[2]), read_only=True) as source:
        return store.read_native_refusal_recording(
            source,
            decision_id=receipt["decision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_actual_admission_to_audited_decision_and_complete_refusal_replay(case):
    receipt = record(case)
    before = hashlib.sha256(case[2].read_bytes()).hexdigest()
    recording = read(case, receipt)
    value = kernel.replay_refusal_entry(
        recording.entry_bytes, expected_decision_id=recording.decision_id
    )
    result = value["result"]
    assert result["failed_stage"] == "publication_admission"
    assert result["reason_codes"][0] == "POINT_IN_TIME_ADMISSION_REJECTED"
    assert "AVAILABILITY_EVIDENCE_UNKNOWN" in result["reason_codes"]
    assert "CANONICAL_CONTRACT_IDENTITY_UNKNOWN" in result["reason_codes"]
    assert result["admission_observed"]
    assert {x["state"] for x in result["input_inventory"]} == {"NOT_ADMITTED"}
    assert not result["strategy_evaluated"] and not result["execution_attempted"]
    assert recording.original_recording_verified
    assert not recording.complete_strategy_replay_asserted
    assert hashlib.sha256(case[2].read_bytes()).hexdigest() == before


def test_first_write_retry_refuses_before_source_io_without_poisoning_original(case):
    receipt = record(case)
    with (
        duckdb.connect(str(case[2])) as target,
        pytest.raises(
            kernel.NativeDecisionRejected,
            match="ATTEMPT_FIRST_WRITE_ONLY",
        ),
    ):
        store.record_native_refusal(None, target, request=case[1], actor_id="synthetic")
    assert read(case, receipt).original_recording_verified


def test_early_unknown_switch_is_audited_without_source_probe(tmp_path):
    at = datetime(2026, 1, 1, tzinfo=UTC)
    request = kernel.RefusalRequest("early", "a" * 64, "b" * 64, at, at, "c" * 40)
    path = tmp_path / "early.duckdb"
    with duckdb.connect(str(path)) as target:
        receipt = store.record_native_refusal(
            object(), target, request=request, actor_id="synthetic", initialize=True
        )
    with duckdb.connect(str(path), read_only=True) as source:
        recorded = store.read_native_refusal_recording(
            source,
            decision_id=receipt["decision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
    value = kernel.replay_refusal_entry(
        recorded.entry_bytes, expected_decision_id=receipt["decision_id"]
    )
    assert value["result"]["reason_codes"] == ["KILL_SWITCH_STATE_UNKNOWN"]
    assert value["frozen_input"]["admission_receipts_hex"] == []


def test_final_audit_failure_preserves_unusable_domain_and_no_retry_adoption(case, monkeypatch):
    lab, request, path = case
    original = AuditLedger.transition
    with lab.opened("publications") as (publications,), duckdb.connect(str(path)) as target:

        def fail_final(self, job, state, reason_code=None):
            if self.conn is target and state == JobState.SUCCEEDED:
                raise OSError("SYNTHETIC_FINAL_AUDIT_FAILURE")
            return original(self, job, state, reason_code)

        with monkeypatch.context() as patch:
            patch.setattr(AuditLedger, "transition", fail_final)
            with pytest.raises(OSError, match="SYNTHETIC_FINAL_AUDIT_FAILURE"):
                store.record_native_refusal(
                    publications, target, request=request, actor_id="synthetic", initialize=True
                )
        decisions = store.name(target, "native_decisions", "decisions")
        row = target.execute(f"SELECT decision_id FROM {decisions}").fetchone()
        assert row is not None
        with pytest.raises(kernel.NativeDecisionRejected, match="ATTEMPT_FIRST_WRITE_ONLY"):
            store.record_native_refusal(None, target, request=request, actor_id="synthetic")
    with (
        duckdb.connect(str(path), read_only=True) as source,
        pytest.raises(
            kernel.NativeDecisionRejected,
            match="ORIGINAL_AUDIT_NOT_SUCCESSFUL",
        ),
    ):
        store.read_native_refusal_recording(
            source, decision_id=row[0], expected_recording_fingerprint="0" * 64
        )


def test_domain_link_failure_rolls_back_and_prior_failed_job_remains_blocker(case):
    lab, request, path = case
    with lab.opened("publications") as (publications,), duckdb.connect(str(path)) as target:
        store._initialize(target)
        attempts = store.name(target, "native_decisions", "attempts")
        decisions = store.name(target, "native_decisions", "decisions")
        target.execute(f"ALTER TABLE {attempts} ADD COLUMN fault INTEGER DEFAULT 1")
        with pytest.raises(duckdb.Error):
            store.record_native_refusal(publications, target, request=request, actor_id="synthetic")
        assert target.execute(f"SELECT count(*) FROM {decisions}").fetchone() == (0,)
        with pytest.raises(kernel.NativeDecisionRejected, match="PRIOR_OBLIGATION_REVIEW_REQUIRED"):
            store.record_native_refusal(None, target, request=request, actor_id="synthetic")


def test_operational_source_failure_is_not_manufactured_policy_decision(case):
    lab, request, path = case
    with lab.opened("publications", writable=True) as (source,):
        records = table(source, "gold", "quote_bundle_publications")
        source.execute(f"DROP TABLE {records}")
    with lab.opened("publications") as (publications,), duckdb.connect(str(path)) as target:
        with pytest.raises(duckdb.Error):
            store.record_native_refusal(
                publications, target, request=request, actor_id="synthetic", initialize=True
            )
        records = store.name(target, "native_decisions", "decisions")
        assert target.execute(f"SELECT count(*) FROM {records}").fetchone() == (0,)


def test_original_refusal_replays_after_current_publication_changes(case):
    receipt = record(case)
    original = read(case, receipt).entry_bytes
    with case[0].opened("publications", writable=True) as (source,):
        records = table(source, "gold", "quote_bundle_publications")
        source.execute(f"UPDATE {records} SET published_at=published_at + INTERVAL '1 second'")
    assert read(case, receipt).entry_bytes == original
    with case[0].opened("publications") as (source,):
        now = evaluate_native_refusal(source, request=case[1])
    assert kernel.replay_refusal_entry(now, expected_decision_id=kernel.sha(now))["result"][
        "reason_codes"
    ] == ["REVIEWED_PUBLICATION_EVIDENCE_PIN_MISMATCH"]


def test_unlinked_scoped_work_and_corrupt_bytes_are_not_old_good_cache(case):
    receipt = record(case)
    assert read(case, receipt).original_recording_verified
    with duckdb.connect(str(case[2])) as target:
        decisions = store.name(target, "native_decisions", "decisions")
        row = target.execute(f"SELECT attempt_key FROM {decisions}").fetchone()
        assert row is not None
        ledger = AuditLedger(target)
        job = ledger.plan_job(
            command_name=store.COMMAND,
            actor_id="synthetic",
            code_revision=case[1].reviewed_code_revision,
            scope_ref="sha256:" + row[0],
            config_hash="0" * 64,
        )
        ledger.transition(job, JobState.FAILED, "EXECUTION_ERROR")
    with pytest.raises(kernel.NativeDecisionRejected, match="ATTEMPT_COVERAGE_REVIEW_REQUIRED"):
        read(case, receipt)


def test_stored_entry_and_recording_fingerprints_are_both_pinned(case):
    receipt = record(case)
    wrong = receipt | dict(recording_fingerprint="0" * 64)
    with pytest.raises(kernel.NativeDecisionRejected, match="RECORDING_FINGERPRINT_CHANGED"):
        read(case, wrong)
    with duckdb.connect(str(case[2])) as target:
        records = store.name(target, "native_decisions", "decisions")
        target.execute(f"UPDATE {records} SET entry_bytes='bad'::BLOB")
    with pytest.raises(kernel.NativeDecisionRejected):
        read(case, receipt)
