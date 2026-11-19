"""Requires real project A1/FS1a; injected captures never use network."""

import json
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.data_platform.kite_instrument_http import HttpCapture, KiteHttpCredentials
from nse_quant.data_platform.kite_instrument_http_service import (
    HttpAcquisitionRejected,
    acquire_instrument_reference,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def receipt(status=200, *, complete=True, body=b"csv", reason="COMPLETE"):
    return HttpCapture(
        "/instruments",
        NOW,
        NOW,
        NOW if body else None,
        NOW,
        status,
        (("content-type", "text/csv"),),
        True,
        complete,
        reason,
        body,
    )


@pytest.fixture
def database(tmp_path):
    conn = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    try:
        yield conn
    finally:
        conn.close()


def acquire(conn, fetcher, session="test", initialize=True):
    return acquire_instrument_reference(
        conn,
        KiteHttpCredentials("FAKE_KEY", "FAKE_TOKEN"),
        capture_session_id=session,
        actor_id="test",
        code_revision="fixture",
        initialize=initialize,
        fetcher=fetcher,
    )


def latest_state(conn):
    return conn.execute(
        "SELECT state FROM medallion_audit.job_events ORDER BY event_index DESC LIMIT 1"
    ).fetchone()[0]


def test_atomic_lineage(database):
    captured = receipt(body=b"exact-content-coded-body")
    result = acquire(database, lambda *args, **kwargs: captured)
    store = BronzeEventStore(database)
    table = store.object_name("event_variants")
    rows = database.execute(
        f"SELECT source_record_id,payload,exchange_ts FROM {table} ORDER BY ingest_sequence"
    ).fetchall()
    assert len(rows) == 2 and bytes(rows[0][1]) == captured.raw_body
    assert rows[0][0] == "response-body" and rows[0][2] is None
    metadata = json.loads(bytes(rows[1][1]))
    assert metadata["body_capture_event_id"] == result.body_capture_event_id
    assert metadata["body_envelope_hash"] == result.body_envelope_hash
    assert metadata["receipt_time_semantics"] == "LOCAL_CAPTURE_END_NOT_EXCHANGE_OR_PUBLICATION"
    assert metadata["provider_published_at"] is None
    assert metadata["platform_published_at"] is None
    assert metadata["csv_validated"] is False
    assert b"FAKE_TOKEN" not in rows[1][1]
    assert latest_state(database) == "SUCCEEDED"
    artifact = database.execute(
        f"SELECT artifact_bytes FROM {store.object_name('input_artifacts')}"
    ).fetchone()
    assert bytes(artifact[0]) == captured.raw_body


def test_no_refetch_for_same_session(database):
    calls = []

    def fetch(*args, **kwargs):
        calls.append(1)
        return receipt()

    acquire(database, fetch)
    with pytest.raises(ValueError, match="CAPTURE_SESSION_ALREADY_ATTEMPTED"):
        acquire(database, fetch, initialize=False)
    assert calls == [1]
    assert database.execute("SELECT count(*) FROM medallion_audit.jobs").fetchone() == (1,)


@pytest.mark.parametrize(
    "captured,expected",
    [
        (receipt(403, body=b"denied"), "HTTP_STATUS_REJECTED"),
        (receipt(200, complete=False, body=b"prefix", reason="HTTP_TIMEOUT"), "HTTP_TIMEOUT"),
        (receipt(200, body=b""), "EMPTY_RESPONSE"),
    ],
)
def test_rejected_evidence_and_failed_audit(database, captured, expected):
    with pytest.raises(HttpAcquisitionRejected) as error:
        acquire(database, lambda *args, **kwargs: captured)
    assert error.value.result.status == "REJECTED"
    assert error.value.result.reason_code == expected
    table = BronzeEventStore(database).object_name("event_variants")
    assert database.execute(f"SELECT count(*) FROM {table}").fetchone() == (2,)
    assert latest_state(database) == "FAILED"
    before = database.execute(
        "SELECT job_id,state FROM medallion_audit.job_events ORDER BY event_index"
    ).fetchall()
    with pytest.raises(ValueError, match="CAPTURE_SESSION_ALREADY_ATTEMPTED"):
        acquire(database, lambda *args, **kwargs: receipt(), initialize=False)
    assert (
        database.execute(
            "SELECT job_id,state FROM medallion_audit.job_events ORDER BY event_index"
        ).fetchall()
        == before
    )


def test_second_insert_failure_rolls_back_batch(database):
    class FaultConnection:
        def __init__(self, conn):
            self.conn = conn
            self.inserts = 0

        def execute(self, sql, *args, **kwargs):
            if sql.lstrip().startswith("INSERT INTO") and '"event_variants"' in sql:
                self.inserts += 1
                if self.inserts == 2:
                    raise RuntimeError("INJECTED_SECOND_EVENT_INSERT")
            return self.conn.execute(sql, *args, **kwargs)

    wrapper = FaultConnection(database)
    with pytest.raises(RuntimeError, match="INJECTED_SECOND_EVENT_INSERT"):
        acquire(wrapper, lambda *args, **kwargs: receipt())
    assert wrapper.inserts == 2
    store = BronzeEventStore(database)
    for name in ("event_variants", "input_artifacts", "ingest_batches"):
        count = database.execute(f"SELECT count(*) FROM {store.object_name(name)}").fetchone()
        assert count == (0,)
    assert latest_state(database) == "FAILED"


def test_fetcher_failure_has_no_success(database):
    def fail(*args, **kwargs):
        raise RuntimeError("INJECTED_FETCHER")

    with pytest.raises(RuntimeError, match="INJECTED_FETCHER"):
        acquire(database, fail)
    assert latest_state(database) == "FAILED"
    table = BronzeEventStore(database).object_name("event_variants")
    assert database.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
