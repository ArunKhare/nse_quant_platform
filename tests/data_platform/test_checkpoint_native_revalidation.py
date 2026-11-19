"""Actual native checkpoint/receipt/policy revalidation on disposable fixtures."""

import hashlib
import json
from dataclasses import asdict, replace

import duckdb
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_identity_statement_reader_native import source_claim as source_claim
from test_recorded_statement_signature_native import inputs
from test_signature_receipt_reader_native import proof_store as proof_store

from nse_quant.data_platform import checkpoint_native_revalidation as reader
from nse_quant.data_platform import native_policy_window as native
from nse_quant.data_platform import policy_checkpoint_store as store
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.policy_window import PolicyPosition
from nse_quant.data_platform.signed_policy_window import SignedPolicyInput
from nse_quant.data_platform.statement_scope_policy import (
    VERSION,
    ScopeQuery,
    policy_signing_message,
)


@pytest.fixture
def checkpoint_case(source_claim, proof_store, tmp_path):
    connections: list[duckdb.DuckDBPyConnection] = []

    def build(record_other_query=False):
        claim = source_claim()
        args, _ = proof_store(inputs(claim))
        request = args["request"]
        query = ScopeQuery(
            request.namespace,
            request.external_id,
            request.asset_kind,
            request.asserted_issuer,
            request.assertion,
            args["expected_public_key_sha256"],
        )
        recorded_query = replace(query, external_id="OTHER") if record_other_query else query
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes_raw()

        def snapshot(sequence):
            raw = json.dumps(
                dict(
                    schema=VERSION,
                    policy_id="SYNTHETIC",
                    sequence=sequence,
                    grants=[dict(grant_id="g1", **asdict(query))],
                    denied_keys=[],
                ),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            return SignedPolicyInput(
                raw, private.sign(policy_signing_message(raw)), hashlib.sha256(raw).hexdigest()
            )

        one, two, three = (snapshot(i) for i in (1, 2, 3))
        policies = dict(
            snapshots=(one, two),
            governance_public_key=public,
            expected_governance_key_sha256=hashlib.sha256(public).hexdigest(),
            anchor=PolicyPosition(1, one.expected_policy_sha256),
            tip=PolicyPosition(2, two.expected_policy_sha256),
        )
        conn = duckdb.connect(str(tmp_path / "checkpoint.duckdb"))
        connections.append(conn)
        record_args = dict(
            **policies,
            query=recorded_query,
            expected_previous_id=None,
            actor_id="test",
            code_revision="synthetic",
        )
        saved = store.record_policy_checkpoint(conn, **record_args, initialize=True)
        view = store.read_policy_checkpoint(
            conn,
            policy_id="SYNTHETIC",
            governance_key_sha256=policies["expected_governance_key_sha256"],
        )
        supplied = dict(args)
        supplied.update({k: v for k, v in policies.items() if k not in {"anchor", "tip"}})
        supplied.update(
            checkpoint=conn,
            policy_id="SYNTHETIC",
            recording_query=recorded_query,
            expected_checkpoint_id=saved["checkpoint_id"],
            expected_history_fingerprint=view.evidence_fingerprint,
        )

        def retry():
            return store.record_policy_checkpoint(conn, **record_args)

        def advance():
            next_args = dict(record_args)
            next_args.update(
                snapshots=(two, three),
                anchor=PolicyPosition(2, two.expected_policy_sha256),
                tip=PolicyPosition(3, three.expected_policy_sha256),
                expected_previous_id=saved["checkpoint_id"],
            )
            return store.record_policy_checkpoint(conn, **next_args)

        return supplied, claim, retry, advance, view

    yield build
    for conn in connections:
        conn.close()


def test_exact_replay_native_and_no_authority_escalation(checkpoint_case):
    args, _, _, _, view = checkpoint_case()
    value = reader.revalidate_checkpoint_native_policy(**args)
    assert value.exact_checkpoint_record_reproduced
    assert value.retained_head_and_native_scope_bound
    assert value.checkpoint_before.evidence_fingerprint == view.evidence_fingerprint
    assert value.checkpoint_after.evidence_fingerprint == view.evidence_fingerprint
    assert not value.policy_currentness_verified
    assert not value.policy_authority_authenticated
    assert not value.issuer_authenticated
    assert not value.namespace_authority_verified
    assert not value.identity_verified
    assert not value.authorized_revocation_asserted
    assert not value.decision_eligibility_asserted
    assert not value.atomic_cross_database_snapshot_asserted
    assert value.canonical_underlying_id is None


def test_recording_query_separate_from_current_assertion_query(checkpoint_case):
    args, _, _, _, _ = checkpoint_case(record_other_query=True)
    value = reader.revalidate_checkpoint_native_policy(**args)
    assert not value.recording_replay.observations[-1].supplied_policy_permits_scope
    assert value.retained_head_and_native_scope_bound


def test_wrong_recording_query_cannot_replay_same_policy_bytes(checkpoint_case):
    args, _, _, _, _ = checkpoint_case()
    args["recording_query"] = replace(args["recording_query"], external_id="OTHER")
    value = reader.revalidate_checkpoint_native_policy(**args)
    assert value.reason_codes == ("EXACT_CHECKPOINT_RECORD_NOT_REPRODUCED",)
    assert value.native_before is None


@pytest.mark.parametrize("field", ["expected_checkpoint_id", "expected_history_fingerprint"])
def test_wrong_reviewed_pin_stops_before_native(checkpoint_case, monkeypatch, field):
    args, _, _, _, _ = checkpoint_case()
    args[field] = "0" * 64

    def forbidden(*positional, **keywords):
        raise AssertionError("Wrong checkpoint pin reached native consumer")

    monkeypatch.setattr(native, "inspect_native_policy_window", forbidden)
    value = reader.revalidate_checkpoint_native_policy(**args)
    assert not value.retained_head_and_native_scope_bound
    assert value.native_before is None


@pytest.mark.parametrize("operation", ["retry", "advance"])
def test_checkpoint_changes_between_reads_never_use_old_good(
    checkpoint_case,
    monkeypatch,
    operation,
):
    args, _, retry, advance, _ = checkpoint_case()
    real = native.inspect_native_policy_window
    calls = 0

    def observe(*positional, **keywords):
        nonlocal calls
        value = real(*positional, **keywords)
        calls += 1
        if calls == 1:
            (retry if operation == "retry" else advance)()
        return value

    monkeypatch.setattr(native, "inspect_native_policy_window", observe)
    value = reader.revalidate_checkpoint_native_policy(**args)
    assert "CHECKPOINT_HEAD_OR_FULL_HISTORY_CHANGED" in value.reason_codes
    assert not value.retained_head_and_native_scope_bound
    assert value.checkpoint_before != value.checkpoint_after


def test_incomplete_audit_after_native_is_retained_as_failure(checkpoint_case, monkeypatch):
    args, _, _, _, view = checkpoint_case()
    real = native.inspect_native_policy_window
    calls = 0

    def observe(*positional, **keywords):
        nonlocal calls
        value = real(*positional, **keywords)
        calls += 1
        if calls == 1:
            AuditLedger(args["checkpoint"]).plan_job(
                command_name=store.COMMAND,
                actor_id="test",
                scope_ref=view.series_id,
                code_revision="synthetic",
                config_hash="e" * 64,
            )
        return value

    monkeypatch.setattr(native, "inspect_native_policy_window", observe)
    value = reader.revalidate_checkpoint_native_policy(**args)
    assert value.reason_codes == ("CHECKPOINT_HISTORY_OR_AUDIT_NOT_COMPLETE_AFTER",)
    assert value.native_before is not None
    assert value.native_after is not None
    assert value.checkpoint_after is None
    assert not value.retained_head_and_native_scope_bound


def test_assertion_retry_between_native_observations_is_not_hidden(checkpoint_case, monkeypatch):
    args, claim, _, _, _ = checkpoint_case()
    real = native.inspect_native_policy_window
    calls = 0

    def observe(*positional, **keywords):
        nonlocal calls
        value = real(*positional, **keywords)
        calls += 1
        if calls == 1:
            claim[5]()
        return value

    monkeypatch.setattr(native, "inspect_native_policy_window", observe)
    value = reader.revalidate_checkpoint_native_policy(**args)
    assert "CHECKPOINT_NATIVE_OBSERVATION_DRIFT" in value.reason_codes
    assert not value.retained_head_and_native_scope_bound


def test_failed_native_recording_cannot_be_rescued_by_checkpoint(checkpoint_case):
    args, claim, _, _, _ = checkpoint_case()
    claim[5](replace(claim[2], assertion="WITHDRAWN"))
    value = reader.revalidate_checkpoint_native_policy(**args)
    assert value.exact_checkpoint_record_reproduced
    assert "CHECKPOINT_NATIVE_SCOPE_NOT_COMPLETE" in value.reason_codes
    assert not value.retained_head_and_native_scope_bound


def test_readonly_checkpoint_handle(checkpoint_case, tmp_path):
    args, _, _, _, _ = checkpoint_case()
    args["checkpoint"].close()
    with duckdb.connect(str(tmp_path / "checkpoint.duckdb"), read_only=True) as conn:
        args["checkpoint"] = conn
        value = reader.revalidate_checkpoint_native_policy(**args)
        assert value.retained_head_and_native_scope_bound
