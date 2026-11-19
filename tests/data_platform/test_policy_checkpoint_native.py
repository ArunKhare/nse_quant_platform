"""Actual AuditLedger/signed-policy/DuckDB integration on synthetic disposable files."""

import duckdb
import pytest
from test_signed_policy_window_integration import signed_window

from nse_quant.data_platform import policy_checkpoint_store as store
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.policy_window import PolicyPosition


def arguments():
    return signed_window([(1, (), "g1"), (2, (), "g2"), (3, (), "g3")])


def first_window(all_args):
    args = dict(all_args)
    args["snapshots"] = args["snapshots"][:2]
    args["tip"] = PolicyPosition(2, args["snapshots"][-1].expected_policy_sha256)
    return args


def advance_window(all_args):
    args = dict(all_args)
    args["snapshots"] = args["snapshots"][1:]
    args["anchor"] = PolicyPosition(2, args["snapshots"][0].expected_policy_sha256)
    return args


def record(conn, args, previous=None, initialize=False):
    return store.record_policy_checkpoint(
        conn,
        **args,
        expected_previous_id=previous,
        actor_id="test",
        code_revision="synthetic",
        initialize=initialize,
    )


def read(conn, args):
    return store.read_policy_checkpoint(
        conn, policy_id="SYNTHETIC", governance_key_sha256=args["expected_governance_key_sha256"]
    )


def test_actual_genesis_retry_advance_and_readonly(tmp_path):
    path = tmp_path / "checkpoint.duckdb"
    args = arguments()
    with duckdb.connect(str(path)) as conn:
        first = record(conn, first_window(args), initialize=True)
        rows = store._name(conn, "policy_checkpoint", "records")
        origin = conn.execute(f"SELECT first_job_id,recorded_at FROM {rows}").fetchone()
        retry = record(conn, first_window(args))
        assert retry["exact_retry"] is True
        assert retry["checkpoint_id"] == first["checkpoint_id"]
        assert conn.execute(f"SELECT first_job_id,recorded_at FROM {rows}").fetchone() == origin
        advanced = record(conn, advance_window(args), first["checkpoint_id"])
        view = read(conn, args)
        assert view.head.checkpoint_id == advanced["checkpoint_id"]
        assert len(view.checkpoint_ids) == 2
        before = view.evidence_fingerprint
        conn.execute("SET TimeZone='Asia/Kolkata'")
        assert read(conn, args).evidence_fingerprint == before
        assert not view.policy_currentness_verified
        assert not view.policy_authority_authenticated
        assert not view.issuer_authenticated
        assert not view.identity_verified
        assert not view.decision_eligibility_asserted
    with duckdb.connect(str(path), read_only=True) as conn:
        assert read(conn, args).evidence_fingerprint == before


def test_actual_denying_tip_is_recordable(tmp_path):
    args = signed_window([(1, (), "g1"), (2, ("a" * 64,), "g2")])
    with duckdb.connect(str(tmp_path / "checkpoint.duckdb")) as conn:
        record(conn, args, initialize=True)
        assert read(conn, args).head.denied_keys == ("a" * 64,)


def test_stale_cas_creates_failed_obligation_not_repairable_by_retry(tmp_path):
    args = arguments()
    with duckdb.connect(str(tmp_path / "checkpoint.duckdb")) as conn:
        record(conn, first_window(args), initialize=True)
        with pytest.raises(ValueError, match="EXPECTED_HEAD"):
            record(conn, advance_window(args))
        with pytest.raises(store.CheckpointReviewRequired, match="AUDIT_OBLIGATION"):
            read(conn, args)
        with pytest.raises(store.CheckpointReviewRequired, match="AUDIT_OBLIGATION"):
            record(conn, first_window(args))


def test_final_audit_failure_does_not_make_committed_row_success(tmp_path, monkeypatch):
    args = arguments()
    real = AuditLedger.transition

    def fail_success(self, job_id, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT_FAILURE")
        return real(self, job_id, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail_success)
    with duckdb.connect(str(tmp_path / "checkpoint.duckdb")) as conn:
        with pytest.raises(RuntimeError, match="SYNTHETIC_FINAL_AUDIT_FAILURE"):
            record(conn, first_window(args), initialize=True)
        count = conn.execute(
            f"SELECT count(*) FROM {store._name(conn, 'policy_checkpoint', 'records')}"
        ).fetchone()
        assert count is not None
        assert count[0] == 1
        with pytest.raises(store.CheckpointReviewRequired, match="AUDIT_OBLIGATION"):
            read(conn, args)


def test_domain_failure_rolls_back_record_and_attempt(tmp_path, monkeypatch):
    args = arguments()

    def reject(*positional, **keywords):
        raise ValueError("SYNTHETIC_DOMAIN_FAILURE")

    monkeypatch.setattr(store, "validate_extension", reject)
    with duckdb.connect(str(tmp_path / "checkpoint.duckdb")) as conn:
        with pytest.raises(ValueError, match="SYNTHETIC_DOMAIN_FAILURE"):
            record(conn, first_window(args), initialize=True)
        for table in ("records", "attempts"):
            count = conn.execute(
                f"SELECT count(*) FROM {store._name(conn, 'policy_checkpoint', table)}"
            ).fetchone()
            assert count is not None
            assert count[0] == 0


def test_corrupt_definition_is_not_adopted(tmp_path):
    with duckdb.connect(str(tmp_path / "checkpoint.duckdb")) as conn:
        store.initialize_policy_checkpoints(conn)
        conn.execute(
            f"UPDATE {store._name(conn, 'policy_checkpoint', 'definitions')} "
            "SET definition_json='tampered'"
        )
        with pytest.raises(ValueError, match="DEFINITION_NOT_ADOPTABLE"):
            store.initialize_policy_checkpoints(conn)
