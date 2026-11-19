"""Real native audit/retention/policy integration; disposable keys and databases only."""

import hashlib

import duckdb
import pytest
from key_lifecycle_fixture import arguments, event, key
from test_lifecycle_scope_policy import policy_arguments

from nse_quant.data_platform import key_lifecycle_capture as store
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.observed_key_lifecycle import KeyLifecycleRejected, sha


@pytest.fixture
def saved(tmp_path):
    root, successor = key(), key()
    args = arguments((event(root, successor, root=root),), root)
    path = tmp_path / "lifecycle.duckdb"
    with duckdb.connect(str(path)) as target:
        receipt = store.capture_key_lifecycle(
            target,
            **args,
            actor_id="synthetic",
            code_revision="synthetic-test",
            initialize=True,
        )
    return path, args, receipt, successor


def read_args(receipt):
    return dict(
        capture_id=receipt["capture_id"],
        expected_evidence_fingerprint=receipt["evidence_fingerprint"],
    )


def test_complete_retained_bytes_native_policy_and_readonly_unchanged(saved):
    path, _, receipt, successor = saved
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with duckdb.connect(str(path), read_only=True) as source:
        retained = store.read_key_lifecycle_capture(source, **read_args(receipt))
        assert retained.recording_verified
        assert sha(retained.input_bytes) == receipt["capture_id"]
        result = store.assess_retained_lifecycle_policy(
            source,
            **read_args(receipt),
            **policy_arguments(successor),
        )
        assert result.supplied_lifecycle_and_policy_constraints_satisfied
        assert not result.root_authority_authenticated
        assert not result.policy_authority_authenticated
        assert not result.decision_eligibility_asserted
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_first_write_only_rejection_does_not_poison_original(saved):
    path, args, receipt, _ = saved
    with duckdb.connect(str(path)) as target:
        events = store._name(target, "medallion_audit", "job_events")
        before = target.execute(f"SELECT count(*) FROM {events}").fetchone()
        with pytest.raises(KeyLifecycleRejected, match="FIRST_WRITE_ONLY"):
            store.capture_key_lifecycle(
                target,
                **args,
                actor_id="synthetic",
                code_revision="test",
                initialize=False,
            )
        assert target.execute(f"SELECT count(*) FROM {events}").fetchone() == before
    with duckdb.connect(str(path), read_only=True) as source:
        assert store.read_key_lifecycle_capture(source, **read_args(receipt)).recording_verified


def test_final_audit_failure_never_adopted_or_healed(tmp_path, monkeypatch):
    root = key()
    args = arguments((event(root, key(), root=root),), root)
    path = tmp_path / "interrupted.duckdb"
    original = AuditLedger.transition
    with duckdb.connect(str(path)) as target:

        def fail_final(self, job_id, state, reason_code=None):
            if self.conn is target and state == JobState.SUCCEEDED:
                raise OSError("SYNTHETIC_FINAL_AUDIT_FAILURE")
            return original(self, job_id, state, reason_code)

        with monkeypatch.context() as patch:
            patch.setattr(AuditLedger, "transition", fail_final)
            with pytest.raises(OSError, match="SYNTHETIC_FINAL_AUDIT_FAILURE"):
                store.capture_key_lifecycle(
                    target,
                    **args,
                    actor_id="synthetic",
                    code_revision="test",
                    initialize=True,
                )
        records = store._name(target, "lifecycle_evidence", "captures")
        row = target.execute(f"SELECT capture_id,evidence_fingerprint FROM {records}").fetchone()
        assert row is not None
        with pytest.raises(KeyLifecycleRejected, match="FIRST_WRITE_ONLY"):
            store.capture_key_lifecycle(
                target,
                **args,
                actor_id="synthetic",
                code_revision="test",
                initialize=False,
            )
    with (
        duckdb.connect(str(path), read_only=True) as source,
        pytest.raises(
            KeyLifecycleRejected,
            match="ORIGINAL_AUDIT_REQUIRED",
        ),
    ):
        store.read_key_lifecycle_capture(
            source,
            capture_id=row[0],
            expected_evidence_fingerprint=row[1],
        )


def test_unlinked_scoped_work_prevents_record_acceptance(saved):
    path, _, receipt, _ = saved
    with duckdb.connect(str(path)) as target:
        ledger = AuditLedger(target)
        job = ledger.plan_job(
            command_name=store.COMMAND,
            actor_id="synthetic",
            code_revision="test",
            scope_ref="sha256:" + receipt["capture_id"],
            config_hash=store.DEFINITION_SHA256,
        )
        ledger.transition(job, JobState.FAILED, "EXECUTION_ERROR")
    with (
        duckdb.connect(str(path), read_only=True) as source,
        pytest.raises(
            KeyLifecycleRejected,
            match="ATTEMPT_COVERAGE_REQUIRED",
        ),
    ):
        store.read_key_lifecycle_capture(source, **read_args(receipt))


@pytest.mark.parametrize(
    "kind",
    ["payload", "fingerprint", "audit", "schema"],
    ids=["payload", "fingerprint", "audit", "schema"],
)
def test_corruption_does_not_fall_back_to_retained_good_result(saved, kind):
    path, _, receipt, _ = saved
    with duckdb.connect(str(path)) as target:
        if kind in ("payload", "fingerprint"):
            name = store._name(target, "lifecycle_evidence", "captures")
            assignment = (
                "input_bytes='bad'::BLOB"
                if kind == "payload"
                else ("evidence_fingerprint=repeat('0',64)")
            )
            target.execute(f"UPDATE {name} SET {assignment}")
        elif kind == "audit":
            name = store._name(target, "medallion_audit", "job_events")
            target.execute(f"DELETE FROM {name} WHERE state='SUCCEEDED'")
        else:
            name = store._name(target, "lifecycle_evidence", "schema_versions")
            target.execute(f"UPDATE {name} SET definition_bytes='bad'::BLOB")
    with duckdb.connect(str(path), read_only=True) as source, pytest.raises(KeyLifecycleRejected):
        store.read_key_lifecycle_capture(source, **read_args(receipt))


def test_no_memory_legacy_target_or_wrong_pin(saved):
    path, args, receipt, _ = saved
    with (
        duckdb.connect(":memory:") as target,
        pytest.raises(
            KeyLifecycleRejected,
            match="FILE_BACKED_REQUIRED",
        ),
    ):
        store.capture_key_lifecycle(
            target,
            **args,
            actor_id="synthetic",
            code_revision="test",
            initialize=True,
        )
    with (
        duckdb.connect(str(path), read_only=True) as source,
        pytest.raises(
            KeyLifecycleRejected,
            match="RECORD_OR_PIN_MISMATCH",
        ),
    ):
        store.read_key_lifecycle_capture(
            source,
            capture_id=receipt["capture_id"],
            expected_evidence_fingerprint="0" * 64,
        )


def test_exact_quoted_catalog_is_supported(tmp_path):
    root = key()
    args = arguments((event(root, key(), root=root),), root)
    path = tmp_path / "safe.lifecycle.duckdb"
    with duckdb.connect(str(path)) as conn:
        receipt = store.capture_key_lifecycle(
            conn,
            **args,
            actor_id="synthetic",
            code_revision="test",
            initialize=True,
        )
    with duckdb.connect(str(path), read_only=True) as conn:
        assert store.read_key_lifecycle_capture(conn, **read_args(receipt)).recording_verified


def test_domain_link_failure_rolls_back_and_failed_work_prevents_later_adoption(saved):
    path, _, _, _ = saved
    root = key()
    args = arguments((event(root, key(), root=root),), root)
    expected_raw, _observed = store.encode_capture_input(**args)
    new_id = sha(expected_raw)
    with duckdb.connect(str(path)) as target:
        attempts = store._name(target, "lifecycle_evidence", "attempts")
        captures = store._name(target, "lifecycle_evidence", "captures")
        target.execute(f"ALTER TABLE {attempts} ADD COLUMN fault INTEGER DEFAULT 1")
        with pytest.raises(duckdb.Error):
            store.capture_key_lifecycle(
                target,
                **args,
                actor_id="synthetic",
                code_revision="test",
                initialize=False,
            )
        assert (
            target.execute(
                f"SELECT 1 FROM {captures} WHERE capture_id=?",
                [new_id],
            ).fetchone()
            is None
        )
        with pytest.raises(KeyLifecycleRejected, match="PRIOR_OBLIGATION_REVIEW_REQUIRED"):
            store.capture_key_lifecycle(
                target,
                **args,
                actor_id="synthetic",
                code_revision="test",
                initialize=False,
            )


def test_complete_original_result_bytes_not_just_fingerprint_are_replayed(saved):
    path, _, receipt, _ = saved
    with duckdb.connect(str(path)) as target:
        records = store._name(target, "lifecycle_evidence", "captures")
        target.execute(f"UPDATE {records} SET result_bytes='{{}}'::BLOB")
    with (
        duckdb.connect(str(path), read_only=True) as source,
        pytest.raises(
            KeyLifecycleRejected,
            match="COMPLETE_REPLAY_MISMATCH",
        ),
    ):
        store.read_key_lifecycle_capture(source, **read_args(receipt))
