"""Actual native store/ledger integration with synthetic payloads, NOT acquisition E2E."""

import hashlib
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore
from nse_quant.data_platform.bronze_support_reader import (
    BronzeSupportPin,
    IngestAuditExpectation,
    inspect_bronze_support,
)

T = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def native_source(tmp_path):
    conn = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    ledger = AuditLedger(conn)
    ledger.initialize()
    store = BronzeEventStore(conn)
    store.initialize()
    payload = b"synthetic supporting bytes"
    event = BronzeEvent("test", "session", "one", T, payload, "bytes", "historical_import")
    expectation = IngestAuditExpectation("test.support_ingest@1", "sha256:" + "c" * 64, "d" * 64)

    def append(events, batch_key, artifact):
        job = ledger.plan_job(
            command_name=expectation.command_name,
            actor_id="test",
            scope_ref=expectation.scope_ref,
            config_hash=expectation.config_hash,
            code_revision="a331f45",
        )
        with ledger.execution(job):
            receipt = store.append_batch(
                events, batch_key=batch_key, input_artifact=artifact, job_id=job
            )
        return receipt

    append((event,), "first", payload)

    def pin(value):
        return BronzeSupportPin(
            value.capture_event_id,
            value.envelope_hash,
            value.payload_hash,
            0,
            len(value.payload),
            hashlib.sha256(value.payload).hexdigest(),
        )

    def inspect(value=None):
        return inspect_bronze_support(
            conn,
            support=pin(event if value is None else value),
            expected_audit=expectation,
        )

    yield conn, event, append, inspect
    conn.close()


def test_actual_fresh_batch_and_exact_retry_scoped_audits(native_source):
    _, event, append, inspect = native_source
    first = inspect()
    assert first.status == "verified_storage_evidence"
    receipt = append((event,), "first", event.payload)
    assert receipt.already_committed
    after = inspect()
    assert after.status == "verified_storage_evidence"
    assert after.evidence_fingerprint != first.evidence_fingerprint
    assert not after.retry_link_coverage_verified
    assert not after.artifact_to_event_semantics_verified
    assert not after.identity_verified


def test_native_conflict_is_preserved_and_blocks_old_pin(native_source):
    _, event, append, inspect = native_source
    conflict = BronzeEvent(
        event.source,
        event.capture_session_id,
        event.source_record_id,
        T,
        b"different",
        "bytes",
        "historical_import",
    )
    receipt = append((conflict,), "conflict", conflict.payload)
    assert receipt.conflict_variants == 1
    assert inspect().status == "review_required"


def test_native_mixed_retry_batch_not_reconstructed_from_first_links(native_source):
    _, event, append, inspect = native_source
    new = BronzeEvent("test", "session", "two", T, b"new", "bytes", "historical_import")
    receipt = append((event, new), "mixed", b"synthetic mixed input artifact")
    assert receipt.exact_retries == 1
    assert receipt.inserted_variants == 1
    result = inspect(new)
    assert result.status == "review_required"
    assert result.current_payload_integrity_verified
    assert not result.fresh_batch_membership_verified


def test_native_artifact_origin_reuse_requires_review(native_source):
    _, event, append, inspect = native_source
    new = BronzeEvent("test", "session", "two", T, b"new", "bytes", "historical_import")
    append((new,), "reuse", event.payload)
    result = inspect(new)
    assert result.status == "review_required"
    assert result.fresh_batch_membership_verified
    assert not result.retained_input_artifact_verified


def test_underlying_request_adapter_does_not_claim_recording_or_identity(native_source):
    from nse_quant.data_platform.underlying_assertion import UnderlyingAssertionRequest
    from nse_quant.data_platform.underlying_support_adapter import (
        inspect_underlying_support_storage,
    )

    conn, event, _, _ = native_source
    request = UnderlyingAssertionRequest(
        "TEST_NAMESPACE",
        "TEST_ASSET",
        "INDEX",
        "TEST_ISSUER",
        "ASSERTED",
        event.capture_event_id,
        event.envelope_hash,
        event.payload_hash,
        0,
        len(event.payload),
        hashlib.sha256(event.payload).hexdigest(),
        "SYNTHETIC_ONLY",
    )
    result = inspect_underlying_support_storage(
        conn,
        request=request,
        expected_audit=IngestAuditExpectation(
            "test.support_ingest@1", "sha256:" + "c" * 64, "d" * 64
        ),
    )
    assert result.status == "verified_storage_evidence"
    assert not result.identity_verified
    assert not result.source_acquisition_authenticity_asserted
