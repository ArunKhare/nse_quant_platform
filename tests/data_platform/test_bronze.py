"""Real DuckDB tests for byte preservation, atomic batches and retry/conflict identity."""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from typing import cast

import duckdb
import pytest

from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore
from nse_quant.data_platform.bronze_import import main, parse_events


def event():
    return BronzeEvent(
        source="fixture",
        capture_session_id="session-1",
        source_record_id="receipt-1",
        received_at=datetime(2026, 10, 30, 9, 15, tzinfo=UTC),
        payload=b"\x00original\xff",
        payload_format="binary",
        origin_kind="historical_import",
    )


@pytest.fixture
def store():
    conn = duckdb.connect(":memory:")
    result = BronzeEventStore(conn)
    result.initialize()
    try:
        yield result
    finally:
        conn.close()


def append(store, events=None, key="batch-1", artifact=b"fixture-artifact"):
    return store.append_batch(
        events if events is not None else (event(),),
        batch_key=key,
        input_artifact=artifact,
        job_id="job-1",
    )


def count(store, table="event_variants"):
    row = store.conn.execute("SELECT count(*) FROM bronze." + table).fetchone()
    assert row is not None
    return row[0]


def test_constructor_has_no_writes():
    conn = duckdb.connect(":memory:")
    try:
        BronzeEventStore(conn)
        assert conn.execute("SHOW TABLES").fetchall() == []
    finally:
        conn.close()


def test_existing_unrelated_data_rejected_without_schema_mutation():
    conn = duckdb.connect(":memory:")
    try:
        conn.execute("CREATE TABLE original_data AS SELECT 42 AS value")
        with pytest.raises(ValueError, match="dedicated"):
            BronzeEventStore(conn).initialize()
        assert conn.execute("SELECT * FROM original_data").fetchall() == [(42,)]
        assert (
            conn.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name='bronze'"
            ).fetchall()
            == []
        )
    finally:
        conn.close()


def test_exact_payload_and_input_artifact_preserved(store):
    receipt = append(store)
    row = store.conn.execute(
        "SELECT payload, received_at, exchange_ts FROM bronze.event_variants"
    ).fetchone()
    assert row is not None
    assert bytes(row[0]) == event().payload
    assert row[1] == event().received_at and row[2] is None
    artifact = store.conn.execute("SELECT artifact_bytes FROM bronze.input_artifacts").fetchone()
    assert artifact is not None and bytes(artifact[0]) == b"fixture-artifact"
    assert receipt.inserted_variants == 1


def test_batch_exact_retry_returns_no_new_writes(store):
    first = append(store)
    retry = append(store)
    assert retry.already_committed and retry.inserted_variants == 0
    assert retry.exact_retries == 1 and retry.last_sequence == first.last_sequence
    assert count(store) == 1 and count(store, "ingest_batches") == 1


def test_retry_in_another_batch_and_duplicate_in_same_batch(store):
    receipt = append(store, (event(), event()))
    assert receipt.inserted_variants == 1 and receipt.exact_retries == 1
    later = append(store, key="batch-2")
    assert later.inserted_variants == 0 and later.exact_retries == 1
    assert count(store) == 1 and count(store, "ingest_batches") == 2


def test_conflict_preserves_original_and_alternative(store):
    append(store)
    changed = replace(event(), payload=b"corrected")
    receipt = append(store, (changed,), key="batch-2", artifact=b"correction-artifact")
    assert receipt.conflict_variants == 1 and count(store) == 2
    payloads = store.conn.execute(
        "SELECT payload FROM bronze.event_variants ORDER BY ingest_sequence"
    ).fetchall()
    assert [bytes(row[0]) for row in payloads] == [event().payload, b"corrected"]
    assert store.conflicting_event_ids() == (event().capture_event_id,)


def test_metadata_change_is_also_a_conflict(store):
    append(store)
    changed = replace(event(), received_at=event().received_at + timedelta(seconds=1))
    assert append(store, (changed,), key="batch-2").conflict_variants == 1
    assert count(store) == 2


def test_new_receipt_identity_does_not_collapse_identical_ticks(store):
    receipt = append(store, (event(), replace(event(), source_record_id="receipt-2")))
    assert receipt.inserted_variants == 2 and receipt.conflict_variants == 0


def test_changed_batch_content_fails_without_overwriting(store):
    append(store)
    with pytest.raises(ValueError, match="Batch identity"):
        append(store, (replace(event(), payload=b"changed"),))
    assert count(store) == 1 and count(store, "ingest_batches") == 1


def test_equivalent_timezones_have_identical_envelopes():
    ist = timezone(timedelta(hours=5, minutes=30))
    assert (
        event().envelope_hash
        == replace(
            event(),
            received_at=event().received_at.astimezone(ist),
        ).envelope_hash
    )


def test_naive_time_and_nonbyte_payload_rejected():
    with pytest.raises(ValueError):
        replace(event(), received_at=datetime(2026, 10, 30))
    with pytest.raises(TypeError):
        replace(event(), payload="not-bytes")


def test_limits_reject_before_writes(store):
    with pytest.raises(ValueError):
        store.append_batch(
            (event(),), batch_key="batch", input_artifact=b"a", job_id="job", max_payload_bytes=1
        )
    assert count(store) == 0
    with pytest.raises(ValueError):
        append(store, events=())


def test_transaction_rolls_back_all_events_artifact_and_batch(store):
    class FailingConnection:
        def __init__(self, real):
            self.real = real
            self.inserts = 0

        def execute(self, sql, parameters=None):
            if "INSERT INTO" in sql and "event_variants" in sql:
                self.inserts += 1
                if self.inserts == 2:
                    raise RuntimeError("injected write failure")

            if parameters is not None:
                return self.real.execute(sql, parameters)

            return self.real.execute(sql)

    connection = FailingConnection(store.conn)
    faulty = BronzeEventStore(cast(duckdb.DuckDBPyConnection, connection))

    with pytest.raises(RuntimeError, match="injected"):
        append(
            faulty,
            (
                event(),
                replace(event(), source_record_id="receipt-2"),
            ),
        )

    assert connection.inserts == 2
    assert count(store) == 0
    assert count(store, "input_artifacts") == 0
    assert count(store, "ingest_batches") == 0

    # The connection remains usable after rollback.
    assert append(store).inserted_variants == 1


def test_initialize_retry_and_unknown_schema(store):
    store.initialize()
    store.conn.execute("UPDATE bronze.schema_versions SET version=99")
    with pytest.raises(ValueError, match="Unsupported"):
        store.initialize()


def encoded_event():
    return {
        "envelope_version": 1,
        "source": "fixture",
        "capture_session_id": "session-1",
        "source_record_id": "record-1",
        "received_at": "2026-10-30T09:15:00+00:00",
        "payload_base64": base64.b64encode(b'{"price":100}').decode(),
        "payload_format": "decoded_provider_json",
        "origin_kind": "historical_import",
    }


def test_parse_preserves_exact_payload_and_missing_exchange_time():
    raw = json.dumps(encoded_event()).encode() + b"\n"
    events = parse_events(raw)
    assert events[0].payload == b'{"price":100}' and events[0].exchange_ts is None


@pytest.mark.parametrize(
    "change",
    [
        {"envelope_version": 2},
        {"payload_base64": "%%%"},
        {"received_at": "2026-10-30T09:15:00"},
        {"unknown_field": "value"},
        {"origin_kind": "pretend"},
    ],
)
def test_invalid_import_envelopes(change):
    value = encoded_event()
    value.update(change)
    with pytest.raises(ValueError):
        parse_events(json.dumps(value).encode())


def test_import_plan_does_not_create_db_or_manifests(tmp_path, capsys):
    source = tmp_path / "events.jsonl"
    source.write_bytes(json.dumps(encoded_event()).encode())
    database = tmp_path / "bronze.duckdb"
    manifests = tmp_path / "manifests"
    assert (
        main(
            [
                "--input",
                str(source),
                "--bronze-db",
                str(database),
                "--manifest-root",
                str(manifests),
                "--batch-key",
                "batch-1",
            ]
        )
        == 0
    )
    assert '"PLANNED"' in capsys.readouterr().out
    assert not database.exists() and not manifests.exists()
