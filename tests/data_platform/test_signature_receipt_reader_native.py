"""Real Bronze/audit/JSONL and signature composition on synthetic disposable inputs."""

import base64
import contextlib
import io
import json
from dataclasses import replace

import duckdb
import pytest
from test_identity_statement_reader_native import source_claim as source_claim
from test_recorded_statement_signature_native import inputs

from nse_quant.data_platform import bronze_import
from nse_quant.data_platform import bronze_jsonl_recompute as codec
from nse_quant.data_platform import recorded_statement_signature as binding
from nse_quant.data_platform import signature_artifact as artifact
from nse_quant.data_platform import signature_receipt_reader as reader
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.data_platform.bronze_support_reader import BronzeSupportPin
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy


@pytest.fixture
def proof_store(tmp_path):
    connections: list[duckdb.DuckDBPyConnection] = []

    def build(args, *, payload_format=artifact.PAYLOAD_FORMAT, **changes):
        value = dict(
            schema=artifact.VERSION,
            assertion_id=args["assertion_id"],
            record_id=args["record_id"],
            payload_sha256=codec.sha(args["payload"]),
            public_key_base64=base64.b64encode(args["public_key"]).decode(),
            signature_base64=base64.b64encode(args["signature"]).decode(),
        )
        value.update(changes)
        proof = codec.canonical(value).encode()
        envelope = dict(
            envelope_version=1,
            source="synthetic_proof",
            capture_session_id="synthetic",
            source_record_id="proof",
            received_at="2026-01-01T00:00:00+00:00",
            payload_base64=base64.b64encode(proof).decode(),
            payload_format=payload_format,
            origin_kind="historical_import",
        )
        raw = codec.canonical(envelope).encode() + b"\n"
        input_path = tmp_path / "proof.jsonl"
        db_path = tmp_path / "proof.duckdb"
        input_path.write_bytes(raw)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert (
                bronze_import.main(
                    [
                        "--input",
                        str(input_path),
                        "--bronze-db",
                        str(db_path),
                        "--manifest-root",
                        str(tmp_path / "unused"),
                        "--batch-key",
                        "proof-batch",
                        "--actor",
                        "test",
                        "--code-revision",
                        "synthetic-test",
                        "--initialize",
                    ]
                )
                == 0
            )
        plan = codec.canonical(json.loads(output.getvalue())["plan"]).encode()
        events = bronze_import.parse_events(raw)
        conn = duckdb.connect(str(db_path))
        connections.append(conn)
        store = BronzeEventStore(conn)
        store.initialize()
        ledger = AuditLedger(conn)
        ledger.initialize()
        ledger.register_contract(
            DatasetContract(
                "bronze.event_variants",
                "1",
                Layer.BRONZE,
                WritePolicy.APPEND_OBSERVATIONS,
                ("capture_event_id", "envelope_hash"),
                (
                    "capture_event_id",
                    "envelope_hash",
                    "received_at",
                    "recorded_at",
                    "source",
                    "payload_hash",
                ),
                "capture",
            )
        )

        def append():
            job = ledger.plan_job(
                command_name=codec.COMMAND,
                actor_id="test",
                code_revision="synthetic-test",
                scope_ref="sha256:" + codec.sha(plan),
                config_hash=codec.CONFIG_HASH,
            )
            with ledger.execution(job):
                store.append_batch(events, batch_key="proof-batch", input_artifact=raw, job_id=job)

        append()
        event = events[0]
        support = BronzeSupportPin(
            event.capture_event_id,
            event.envelope_hash,
            event.payload_hash,
            0,
            len(proof),
            codec.sha(proof),
        )
        supplied = {k: v for k, v in args.items() if k not in {"signature", "public_key"}}
        supplied.update(
            proof_bronze=conn,
            proof_support=support,
            proof_plan=plan,
            expected_proof_plan_sha256=codec.sha(plan),
        )
        return supplied, append

    yield build
    for conn in connections:
        conn.close()


def test_native_proof_receipt_links_but_does_not_authenticate(source_claim, proof_store):
    args, _ = proof_store(inputs(source_claim()))
    value = reader.inspect_signature_receipt(**args)
    assert value.proof_receipt_storage_linkage_verified
    assert value.status == "recorded_signature_proof_storage_linked"
    assert value.binding_before.recorded_payload_signature_bound
    assert value.binding_after.recorded_payload_signature_bound
    repeated = reader.inspect_signature_receipt(**args)
    assert value.evidence_fingerprint == repeated.evidence_fingerprint
    assert not value.signature_acquisition_provenance_verified
    assert not value.source_acquisition_authenticity_asserted
    assert not value.issuer_authenticated
    assert not value.identity_verified
    assert not value.authorized_revocation_asserted
    assert not value.decision_eligibility_asserted
    assert value.canonical_underlying_id is None


def test_wrong_artifact_target_cannot_attach(source_claim, proof_store):
    args, _ = proof_store(inputs(source_claim()), assertion_id="0" * 64)
    value = reader.inspect_signature_receipt(**args)
    assert value.reason_codes == ("SIGNATURE_PROOF_TARGET_MISMATCH",)
    assert value.binding_before is None


def test_wrong_format_never_relabels_history(source_claim, proof_store):
    args, _ = proof_store(inputs(source_claim()), payload_format="text/plain")
    with pytest.raises(artifact.SignatureArtifactRejected, match="FORMAT_OR_WHOLE"):
        reader.inspect_signature_receipt(**args)


def test_partial_proof_span_rejected(source_claim, proof_store):
    args, _ = proof_store(inputs(source_claim()))
    args["proof_support"] = replace(args["proof_support"], byte_start=1)
    with pytest.raises(ValueError, match="WHOLE_PAYLOAD"):
        reader.inspect_signature_receipt(**args)


def test_external_key_pin_still_mandatory(source_claim, proof_store):
    args, _ = proof_store(inputs(source_claim()))
    args["expected_public_key_sha256"] = "0" * 64
    value = reader.inspect_signature_receipt(**args)
    assert not value.proof_receipt_storage_linkage_verified
    assert value.status == "review_required"


def test_actual_proof_retry_between_observations_blocks(source_claim, proof_store, monkeypatch):
    args, append = proof_store(inputs(source_claim()))
    real = binding.inspect_recorded_statement_signature
    calls = 0

    def observe(*positional, **keywords):
        nonlocal calls
        value = real(*positional, **keywords)
        calls += 1
        if calls == 1:
            append()
        return value

    monkeypatch.setattr(binding, "inspect_recorded_statement_signature", observe)
    value = reader.inspect_signature_receipt(**args)
    assert value.status == "review_required"
    assert "SIGNATURE_PROOF_STORAGE_OR_DERIVATION_CHANGED" in value.reason_codes
    assert not value.proof_receipt_storage_linkage_verified


def test_recording_retry_between_bindings_blocks(source_claim, proof_store, monkeypatch):
    claim = source_claim()
    args, _ = proof_store(inputs(claim))
    real = binding.inspect_recorded_statement_signature
    calls = 0

    def observe(*positional, **keywords):
        nonlocal calls
        value = real(*positional, **keywords)
        calls += 1
        if calls == 1:
            claim[5]()
        return value

    monkeypatch.setattr(binding, "inspect_recorded_statement_signature", observe)
    value = reader.inspect_signature_receipt(**args)
    assert value.status == "review_required"
    assert "RECORDED_SIGNATURE_BINDING_NOT_COMPLETE_OR_CHANGED" in value.reason_codes
