"""Actual native orchestration with synthetic source fixture; not issuer/acquisition E2E."""

import hashlib
from dataclasses import asdict, replace

import duckdb
import pytest
from test_bronze_support_native import native_source as native_source

from nse_quant.data_platform import underlying_assertion as kernel
from nse_quant.data_platform import underlying_assertion_store as store
from nse_quant.data_platform import underlying_support_adapter as adapter
from nse_quant.data_platform import underlying_support_revalidation as service
from nse_quant.data_platform.bronze import BronzeEvent
from nse_quant.data_platform.bronze_support_reader import IngestAuditExpectation


@pytest.fixture
def inputs(tmp_path, native_source):
    bronze, event, append, _ = native_source
    target = duckdb.connect(str(tmp_path / "identity.duckdb"))
    request = kernel.UnderlyingAssertionRequest(
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
    expected = IngestAuditExpectation("test.support_ingest@1", "sha256:" + "c" * 64, "d" * 64)

    def record(value=None):
        return store.record_underlying_assertion(
            bronze,
            target,
            request=request if value is None else value,
            actor_id="test",
            code_revision="dee3bc7",
            initialize=True,
        )

    first = record()

    def run(pin=None, value=None, audit=None):
        return service.revalidate_underlying_assertion_support(
            target,
            bronze,
            assertion_id=first["assertion_id"] if pin is None else pin,
            request=request if value is None else value,
            expected_audit=expected if audit is None else audit,
        )

    yield target, bronze, request, expected, first, event, append, record, run
    target.close()


def test_exact_recording_and_current_storage_do_not_mint_identity(inputs):
    _, _, _, _, _, _, _, _, run = inputs
    result = run()
    assert result.status == "verified_recording_and_current_storage"
    assert result.current_support_checked
    assert result.exact_recorded_request_matched
    assert result.registry_unchanged_observed
    assert result.bronze_support_unchanged_observed
    assert result.recording_before.registry_history_verified
    assert result.support_after.scoped_audit_history_verified
    assert result.evidence_fingerprint == run().evidence_fingerprint
    assert not result.identity_verified
    assert not result.issuer_authenticated
    assert result.canonical_underlying_id is None
    assert not result.artifact_to_event_semantics_verified
    assert not result.retry_link_coverage_verified
    assert not result.bronze_acquisition_provenance_verified
    assert not result.availability_evidence_verified
    assert not result.historical_validity_asserted
    assert not result.decision_eligibility_asserted
    assert not result.atomic_cross_database_snapshot_asserted


@pytest.mark.parametrize("kind", ["DISPUTED", "WITHDRAWN"])
def test_latest_non_asserted_statements_can_have_verified_storage_not_authority(inputs, kind):
    _, _, request, _, _, _, _, record, run = inputs
    updated = replace(request, assertion=kind)
    recorded = record(updated)
    result = run(pin=recorded["assertion_id"], value=updated)
    assert result.status == "verified_recording_and_current_storage"
    assert result.recording_before.archived_assertion_kind == kind
    assert not result.identity_verified
    assert not result.issuer_authenticated


def test_old_asserted_retry_cannot_bypass_newer_withdrawal(inputs, monkeypatch):
    _, _, request, _, _, _, _, record, run = inputs
    record(replace(request, assertion="WITHDRAWN"))
    record()

    def forbidden(*args, **kwargs):
        raise AssertionError("Old pin reached source check")

    monkeypatch.setattr(adapter, "inspect_underlying_support_storage", forbidden)
    result = run()
    assert result.status == "review_required"
    assert not result.current_support_checked
    assert result.support_before is None


def test_explicit_request_mismatch_stops_before_database_io(inputs):
    _, _, request, expected, first, _, _, _, _ = inputs
    result = service.revalidate_underlying_assertion_support(
        object(),
        object(),
        assertion_id=first["assertion_id"],
        request=replace(request, rationale_code="DIFFERENT"),
        expected_audit=expected,
    )
    assert result.status == "review_required"
    assert result.reason_codes == ("EXPLICIT_REQUEST_DOES_NOT_MATCH_ASSERTION_PIN",)
    assert not result.current_support_checked


def test_registry_exact_retry_during_support_check_is_detected(inputs, monkeypatch):
    _, _, _, _, _, _, _, record, run = inputs
    original = adapter.inspect_underlying_support_storage
    calls = 0

    def inspect(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            record()
        return result

    monkeypatch.setattr(adapter, "inspect_underlying_support_storage", inspect)
    result = run()
    assert result.status == "review_required"
    assert not result.registry_unchanged_observed
    assert result.bronze_support_unchanged_observed
    assert result.exact_recorded_request_matched


def test_bronze_exact_retry_between_observations_is_detected(inputs, monkeypatch):
    _, _, _, _, _, event, append, _, run = inputs
    original = adapter.inspect_underlying_support_storage
    calls = 0

    def inspect(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            assert append((event,), "first", event.payload).already_committed
        return result

    monkeypatch.setattr(adapter, "inspect_underlying_support_storage", inspect)
    result = run()
    assert result.status == "review_required"
    assert result.registry_unchanged_observed
    assert not result.bronze_support_unchanged_observed
    assert result.support_before.scoped_audit_history_verified
    assert result.support_after.scoped_audit_history_verified


def test_later_bronze_conflict_never_falls_back_to_old_good(inputs, monkeypatch):
    _, _, _, _, _, event, append, _, run = inputs
    original = adapter.inspect_underlying_support_storage
    calls = 0

    def inspect(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            conflict = BronzeEvent(
                event.source,
                event.capture_session_id,
                event.source_record_id,
                event.received_at,
                b"conflict",
                event.payload_format,
                event.origin_kind,
            )
            append((conflict,), "conflict", conflict.payload)
        return result

    monkeypatch.setattr(adapter, "inspect_underlying_support_storage", inspect)
    result = run()
    assert result.status == "review_required"
    assert result.support_before.status == "verified_storage_evidence"
    assert result.support_after.status == "review_required"
    assert not result.bronze_support_unchanged_observed


def test_registry_withdrawal_during_observation_blocks_old_pin(inputs, monkeypatch):
    _, _, request, _, _, _, _, record, run = inputs
    original = adapter.inspect_underlying_support_storage
    calls = 0

    def inspect(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            record(replace(request, assertion="WITHDRAWN"))
        return result

    monkeypatch.setattr(adapter, "inspect_underlying_support_storage", inspect)
    result = run()
    assert result.status == "review_required"
    assert not result.recording_after.pinned_is_last_distinct_statement
    assert not result.registry_unchanged_observed


def test_wrong_audit_expectation_requires_review_not_business_rejection(inputs):
    _, _, _, expected, _, _, _, _, run = inputs
    result = run(audit=replace(expected, config_hash="e" * 64))
    assert result.status == "review_required"
    assert result.current_support_checked
    assert not result.identity_verified
    assert result.support_before.status == result.support_after.status == "review_required"


def test_sql_failures_propagate_instead_of_fabricated_claim_rejections(inputs):
    _, bronze, _, _, _, _, _, _, run = inputs
    table = store._name(bronze, "bronze", "ingest_batches")
    bronze.execute(f"DROP TABLE {table}")
    with pytest.raises(duckdb.Error):
        run()


def test_alias_databases_rejected(inputs):
    target, _, request, expected, first, _, _, _, _ = inputs
    with pytest.raises(ValueError, match="SEPARATE"):
        service.revalidate_underlying_assertion_support(
            target,
            target,
            assertion_id=first["assertion_id"],
            request=request,
            expected_audit=expected,
        )


def test_incomplete_original_recording_not_repaired_by_retry(inputs):
    target, _, _, _, first, _, _, record, run = inputs
    events = store._name(target, "medallion_audit", "job_events")
    target.execute(f"DELETE FROM {events} WHERE job_id=? AND state='SUCCEEDED'", [first["job_id"]])
    record()
    result = run()
    assert result.status == "review_required"
    assert not result.current_support_checked
    assert first["job_id"] in result.recording_before.audit_obligation_job_ids


def test_actual_cli_readonly_operation_and_summary(inputs, tmp_path, capsys):
    from nse_quant.data_platform.underlying_support_revalidation_cli import main

    target, bronze, request, expected, first, _, _, _, _ = inputs
    target_path = target.execute("PRAGMA database_list").fetchone()[2]
    source_path = bronze.execute("PRAGMA database_list").fetchone()[2]
    target.close()
    bronze.close()
    request_file = tmp_path / "reviewed-request.json"
    request_file.write_text(
        kernel.canonical(
            {
                "assertion_request": asdict(request),
                "expected_audit": asdict(expected),
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "--identity-db",
                target_path,
                "--bronze-db",
                source_path,
                "--assertion-id",
                first["assertion_id"],
                "--request-file",
                str(request_file),
                "--revalidate",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "verified_recording_and_current_storage" in output
    assert "request_json" not in output
    assert "synthetic supporting bytes" not in output
