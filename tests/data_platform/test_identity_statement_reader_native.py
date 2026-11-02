"""Native recorded-document integration on synthetic statements, not authenticated issuer E2E."""

import base64
import contextlib
import io
import json
from dataclasses import replace

import duckdb
import pytest

from nse_quant.data_platform import bronze_import
from nse_quant.data_platform import bronze_jsonl_recompute as jsonl_codec
from nse_quant.data_platform import bronze_jsonl_support_reader as jsonl_reader
from nse_quant.data_platform import identity_statement_document as document
from nse_quant.data_platform import identity_statement_reader as reader
from nse_quant.data_platform import underlying_assertion as kernel
from nse_quant.data_platform import underlying_assertion_store as assertions
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy


def body(**changes):
    value = dict(
        statement_schema=document.VERSION,
        record_id="r1",
        namespace="TEST_NS",
        external_id="ASSET1",
        asset_kind="INDEX",
        asserted_issuer="TEST_ISSUER",
        assertion="ASSERTED",
    )
    value.update(changes)
    return document.canonical(value).encode()


@pytest.fixture
def source_claim(tmp_path):
    connections: list[duckdb.DuckDBPyConnection] = []

    def build(
        *,
        payload=None,
        claim_issuer="TEST_ISSUER",
        claim_kind="ASSERTED",
        include_newline=False,
        payload_format=document.PAYLOAD_FORMAT,
    ):
        first_body = body(assertion=claim_kind)
        received = first_body + b"\n" if payload is None else payload
        event_json = dict(
            envelope_version=1,
            source="test_statement",
            capture_session_id="session",
            source_record_id="document",
            received_at="2026-01-01T00:00:00+00:00",
            payload_base64=base64.b64encode(received).decode(),
            payload_format=payload_format,
            origin_kind="historical_import",
        )
        raw = jsonl_codec.canonical(event_json).encode() + b"\n"
        artifact_path, bronze_path = tmp_path / "input.jsonl", tmp_path / "bronze.duckdb"
        artifact_path.write_bytes(raw)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert (
                bronze_import.main(
                    [
                        "--input",
                        str(artifact_path),
                        "--bronze-db",
                        str(bronze_path),
                        "--manifest-root",
                        str(tmp_path / "not-created"),
                        "--batch-key",
                        "batch",
                        "--actor",
                        "test",
                        "--code-revision",
                        "synthetic-test",
                        "--initialize",
                    ]
                )
                == 0
            )
        plan = jsonl_codec.canonical(json.loads(output.getvalue())["plan"]).encode()
        events = bronze_import.parse_events(raw)
        bronze = duckdb.connect(str(bronze_path))
        registry = duckdb.connect(str(tmp_path / "identity.duckdb"))
        connections.extend((bronze, registry))
        store = BronzeEventStore(bronze)
        store.initialize()
        ledger = AuditLedger(bronze)
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
                command_name=jsonl_codec.COMMAND,
                actor_id="test",
                code_revision="synthetic-test",
                scope_ref="sha256:" + jsonl_codec.sha(plan),
                config_hash=jsonl_codec.CONFIG_HASH,
            )
            with ledger.execution(job):
                store.append_batch(events, batch_key="batch", input_artifact=raw, job_id=job)

        append()
        event = events[0]
        end = len(first_body) + (1 if include_newline else 0)
        request = kernel.UnderlyingAssertionRequest(
            "TEST_NS",
            "ASSET1",
            "INDEX",
            claim_issuer,
            claim_kind,
            event.capture_event_id,
            event.envelope_hash,
            event.payload_hash,
            0,
            end,
            document.sha(received[:end]),
            "SYNTHETIC_TEST_ONLY",
        )

        def record(value=None):
            return assertions.record_underlying_assertion(
                bronze,
                registry,
                request=request if value is None else value,
                actor_id="test",
                code_revision="synthetic-test",
                initialize=True,
            )

        saved = record()

        def inspect():
            return reader.inspect_recorded_statement_content(
                registry,
                bronze,
                assertion_id=saved["assertion_id"],
                request=request,
                record_id="r1",
                original_plan=plan,
                expected_plan_sha256=document.sha(plan),
            )

        return registry, bronze, request, saved, plan, record, append, inspect

    yield build
    for conn in connections:
        conn.close()


def test_exact_recorded_text_is_not_authenticated_identity(source_claim):
    _, _, _, _, _, _, _, inspect = source_claim()
    result = inspect()
    assert result.status == "matched_untrusted_statement_support"
    assert result.statement_content_matched
    assert result.exact_record_span_verified
    assert result.jsonl_derivation_verified
    assert not result.identity_verified
    assert not result.issuer_authenticated
    assert result.canonical_underlying_id is None
    assert not result.authorized_revocation_asserted
    assert not result.availability_evidence_verified
    assert not result.historical_validity_asserted
    assert not result.decision_eligibility_asserted
    assert not result.atomic_cross_database_snapshot_asserted
    assert result.evidence_fingerprint == inspect().evidence_fingerprint


@pytest.mark.parametrize("kind", ["DISPUTED", "WITHDRAWN"])
def test_statement_kind_match_is_not_authorized_revocation(source_claim, kind):
    _, _, _, _, _, _, _, inspect = source_claim(claim_kind=kind)
    result = inspect()
    assert result.statement_content_matched
    assert not result.authorized_revocation_asserted
    assert not result.identity_verified


@pytest.mark.parametrize(
    "changes",
    [
        {"claim_issuer": "OTHER"},
        {"include_newline": True},
        {"payload_format": "text/plain"},
    ],
)
def test_storage_and_recording_alone_do_not_match_claim_content(source_claim, changes):
    _, _, _, _, _, _, _, inspect = source_claim(**changes)
    result = inspect()
    assert result.recording_before.status == "verified_recording_and_current_storage"
    assert result.jsonl_before.status == "verified_jsonl_recomputation"
    assert result.status == "review_required"
    assert not result.statement_content_matched


def test_same_subject_document_dispute_not_filtered_out(source_claim):
    payload = body() + b"\n" + body(record_id="r2", assertion="DISPUTED") + b"\n"
    _, _, _, _, _, _, _, inspect = source_claim(payload=payload)
    result = inspect()
    assert result.status == "review_required"
    assert result.content.same_subject_record_ids == ("r1", "r2")
    assert not result.statement_content_matched


def test_unsupported_later_record_blocks_matching_prefix(source_claim):
    _, _, _, _, _, _, _, inspect = source_claim(payload=body() + b"\n{}\n")
    result = inspect()
    assert result.status == "review_required"
    assert result.content is None


def test_old_pin_cannot_reach_content_after_withdrawal(source_claim, monkeypatch):
    _, _, request, _, _, record, _, inspect = source_claim()
    record(replace(request, assertion="WITHDRAWN"))
    record()

    def fail(*args, **kwargs):
        raise AssertionError("Old asserted pin reached content parser")

    monkeypatch.setattr(reader, "match_statement_content", fail)
    result = inspect()
    assert result.status == "review_required"
    assert result.jsonl_before is None
    assert result.content is None


def test_registry_exact_retry_between_observations_requires_review(source_claim, monkeypatch):
    _, _, _, _, _, record, _, inspect = source_claim()
    native = jsonl_reader.inspect_jsonl_bronze_support
    calls = 0

    def checked(*args, **kwargs):
        nonlocal calls
        value = native(*args, **kwargs)
        calls += 1
        if calls == 1:
            record()
        return value

    monkeypatch.setattr(jsonl_reader, "inspect_jsonl_bronze_support", checked)
    assert inspect().status == "review_required"


def test_source_retry_is_not_hidden_between_complete_views(source_claim, monkeypatch):
    _, _, _, _, _, _, append, inspect = source_claim()
    native = jsonl_reader.inspect_jsonl_bronze_support
    calls = 0

    def checked(*args, **kwargs):
        nonlocal calls
        value = native(*args, **kwargs)
        calls += 1
        if calls == 1:
            append()
        return value

    monkeypatch.setattr(jsonl_reader, "inspect_jsonl_bronze_support", checked)
    assert inspect().status == "review_required"


def test_actual_readonly_operation_and_timezone(source_claim):
    registry, bronze, request, saved, plan, _, _, inspect = source_claim()
    before = inspect()
    registry.execute("SET TimeZone='Asia/Kolkata'")
    bronze.execute("SET TimeZone='Asia/Kolkata'")
    assert inspect().evidence_fingerprint == before.evidence_fingerprint
    registry_path = registry.execute("PRAGMA database_list").fetchone()[2]
    bronze_path = bronze.execute("PRAGMA database_list").fetchone()[2]
    registry.close()
    bronze.close()
    with (
        duckdb.connect(registry_path, read_only=True) as target,
        duckdb.connect(bronze_path, read_only=True) as source,
    ):
        result = reader.inspect_recorded_statement_content(
            target,
            source,
            assertion_id=saved["assertion_id"],
            request=request,
            record_id="r1",
            original_plan=plan,
            expected_plan_sha256=document.sha(plan),
        )
        assert result.evidence_fingerprint == before.evidence_fingerprint
