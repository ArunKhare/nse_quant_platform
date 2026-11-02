"""Native parser/store/audit/plan integration on synthetic inputs, NOT provider/issuer E2E."""

import base64
import contextlib
import io
import json

import duckdb
import pytest

from nse_quant.data_platform import bronze_import
from nse_quant.data_platform import bronze_jsonl_recompute as codec
from nse_quant.data_platform import bronze_jsonl_support_reader as reader
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.data_platform.bronze_support_reader import BronzeSupportPin
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy


@pytest.fixture
def imported(tmp_path):
    opened = []

    def build(*, substitution=False, reverse=False, duplicate_key=False):
        rows = [
            dict(
                envelope_version=1,
                source="test",
                capture_session_id="session",
                source_record_id=record,
                received_at="2026-01-01T00:00:00+00:00",
                payload_base64=base64.b64encode(payload).decode(),
                payload_format="bytes",
                origin_kind="historical_import",
            )
            for record, payload in (("one", b"payload-one"), ("two", b"payload-two"))
        ]
        raw = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
        if duplicate_key:
            raw = raw.replace(b'"source":', b'"source":"ignored","source":', 1)
        source_path, target_path = tmp_path / "input.jsonl", tmp_path / "bronze.duckdb"
        source_path.write_bytes(raw)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert (
                bronze_import.main(
                    [
                        "--input",
                        str(source_path),
                        "--bronze-db",
                        str(target_path),
                        "--manifest-root",
                        str(tmp_path / "unused-plan-root"),
                        "--batch-key",
                        "batch",
                        "--actor",
                        "test",
                        "--code-revision",
                        "0646140",
                        "--initialize",
                    ]
                )
                == 0
            )
        # Actual importer PLAN only; no importer execution or manifest writing here.
        plan = codec.canonical(json.loads(output.getvalue())["plan"]).encode()
        events = bronze_import.parse_events(raw)
        if substitution:
            changed = raw.replace(base64.b64encode(b"payload-one"), base64.b64encode(b"substitute"))
            events = bronze_import.parse_events(changed)
        if reverse:
            events = tuple(reversed(events))
        conn = duckdb.connect(str(target_path))
        opened.append(conn)
        store = BronzeEventStore(conn)
        store.initialize()
        ledger = AuditLedger(conn)
        ledger.initialize()
        contract = DatasetContract(
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
        ledger.register_contract(contract)
        job = ledger.plan_job(
            command_name=codec.COMMAND,
            actor_id="test",
            scope_ref="sha256:" + codec.sha(plan),
            code_revision="0646140",
            config_hash=codec.CONFIG_HASH,
        )
        with ledger.execution(job):
            store.append_batch(events, batch_key="batch", input_artifact=raw, job_id=job)
        event = events[0]
        support = BronzeSupportPin(
            event.capture_event_id,
            event.envelope_hash,
            event.payload_hash,
            0,
            len(event.payload),
            codec.sha(event.payload),
        )

        def inspect():
            return reader.inspect_jsonl_bronze_support(
                conn,
                support=support,
                plan_bytes=plan,
                expected_plan_sha256=codec.sha(plan),
            )

        return conn, store, ledger, support, plan, inspect

    yield build
    for conn in opened:
        conn.close()


def test_exact_original_jsonl_recomputes_native_envelopes_payloads_and_plan(imported):
    _, _, _, _, _, inspect = imported()
    value = inspect()
    assert value.status == "verified_jsonl_recomputation"
    assert value.artifact_to_event_semantics_verified
    assert value.original_plan_binding_verified
    assert not value.storage_before.artifact_to_event_semantics_verified
    assert not value.identity_semantics_verified
    assert not value.identity_verified
    assert not value.issuer_authenticated
    assert not value.retry_link_coverage_verified
    assert not value.availability_evidence_verified
    assert not value.historical_validity_asserted
    assert not value.decision_eligibility_asserted
    assert not value.atomic_cross_database_snapshot_asserted
    assert value.evidence_fingerprint == inspect().evidence_fingerprint


@pytest.mark.parametrize("change", ["substitution", "reverse", "duplicate_key"])
def test_self_consistent_storage_does_not_prove_artifact_derivation(imported, change):
    _, _, _, _, _, inspect = imported(**{change: True})
    value = inspect()
    assert value.storage_before.status == "verified_storage_evidence"
    assert value.status == "review_required"
    assert not value.artifact_to_event_semantics_verified
    assert not value.identity_verified


def test_actor_change_not_hidden_by_correct_scope_and_config(imported):
    conn, _, _, _, _, inspect = imported()
    jobs = reader_job_name(conn, "jobs")
    conn.execute(f"UPDATE {jobs} SET actor_id='different'")
    value = inspect()
    assert value.storage_before.status == "verified_storage_evidence"
    assert value.status == "review_required"


def reader_job_name(conn, table):
    from nse_quant.data_platform.bronze_support_reader import _name

    return _name(conn, "medallion_audit", table)


def test_native_contract_required_not_silently_inferred(imported):
    conn, _, _, _, _, inspect = imported()
    conn.execute(f"UPDATE {reader_job_name(conn, 'dataset_contracts')} SET contract_json='{{}}'")
    value = inspect()
    assert value.status == "review_required"
    assert not value.artifact_to_event_semantics_verified


def test_source_sql_failure_is_not_fabricated_identity_rejection(imported):
    conn, _, _, _, _, inspect = imported()
    conn.execute(f"DROP TABLE {reader_job_name(conn, 'dataset_contracts')}")
    with pytest.raises(duckdb.Error):
        inspect()


def test_incomplete_origin_not_healed_by_later_scope_success(imported):
    conn, _, ledger, _, plan, inspect = imported()
    events = reader_job_name(conn, "job_events")
    conn.execute(f"DELETE FROM {events} WHERE state='SUCCEEDED'")
    retry = ledger.plan_job(
        command_name=codec.COMMAND,
        actor_id="test",
        scope_ref="sha256:" + codec.sha(plan),
        code_revision="0646140",
        config_hash=codec.CONFIG_HASH,
    )
    with ledger.execution(retry):
        pass
    value = inspect()
    assert value.status == "review_required"
    assert not value.artifact_to_event_semantics_verified


def test_contract_and_storage_observation_drift_retained(imported, monkeypatch):
    conn, _, _, _, _, inspect = imported()
    actual = reader._observe
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        result = actual(*args, **kwargs)
        calls += 1
        if calls == 1:
            contracts = reader_job_name(conn, "dataset_contracts")
            conn.execute(f"UPDATE {contracts} SET contract_json='{{}}'")
        return result

    monkeypatch.setattr(reader, "_observe", observe)
    value = inspect()
    assert value.derivation_before.status == "verified"
    assert value.derivation_after.status == "review_required"
    assert value.status == "review_required"


def test_timezone_and_real_readonly_current_database(imported):
    conn, _, _, support, plan, inspect = imported()
    before = inspect()
    conn.execute("SET TimeZone='Asia/Kolkata'")
    assert inspect().evidence_fingerprint == before.evidence_fingerprint
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    conn.close()
    with duckdb.connect(path, read_only=True) as source:
        value = reader.inspect_jsonl_bronze_support(
            source,
            support=support,
            plan_bytes=plan,
            expected_plan_sha256=codec.sha(plan),
        )
        assert value.evidence_fingerprint == before.evidence_fingerprint
