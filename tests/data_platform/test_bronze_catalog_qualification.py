"""Regression coverage for catalog/schema collisions on real file-backed databases."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import duckdb
import pytest

from nse_quant.data_platform.bronze import (
    BronzeEvent,
    BronzeEventStore,
    qualified_bronze_name,
)


def event():
    return BronzeEvent(
        source="fixture",
        capture_session_id="session-1",
        source_record_id="receipt-1",
        received_at=datetime(2026, 10, 30, tzinfo=UTC),
        payload=b"original",
        payload_format="binary",
        origin_kind="historical_import",
    )


@pytest.mark.parametrize(
    "filename",
    [
        "bronze.duckdb",
        "capture.duckdb",
        "trader's.duckdb",
        "with.dot.duckdb",
    ],
)
def test_file_catalogs_initialize_append_retry_conflict_and_reopen(tmp_path, filename):
    path = tmp_path / filename
    conn = duckdb.connect(str(path))
    try:
        store = BronzeEventStore(conn)
        store.initialize()
        store.verify_target()
        first = store.append_batch(
            (event(),),
            batch_key="batch-1",
            input_artifact=b"input-1",
            job_id="job-1",
        )
        retry = store.append_batch(
            (event(),),
            batch_key="batch-1",
            input_artifact=b"input-1",
            job_id="job-2",
        )
        conflict = store.append_batch(
            (replace(event(), payload=b"changed"),),
            batch_key="batch-2",
            input_artifact=b"input-2",
            job_id="job-3",
        )
        assert first.inserted_variants == 1 and retry.already_committed
        assert conflict.conflict_variants == 1
        assert store.conflicting_event_ids() == (event().capture_event_id,)
        store.initialize()
    finally:
        conn.close()
    conn = duckdb.connect(str(path), read_only=True)
    try:
        row = conn.execute(
            f"SELECT count(*) FROM {qualified_bronze_name(conn, 'event_variants')}"
        ).fetchone()
        assert row is not None and row[0] == 2
    finally:
        conn.close()


def test_atomic_rollback_in_catalog_named_bronze(tmp_path):
    conn = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    try:
        store = BronzeEventStore(conn)
        store.initialize()

        class FailingConnection:
            def __init__(self, real):
                self.real = real
                self.inserts = 0

            def execute(self, sql, parameters=None):
                if "INSERT INTO" in sql and "event_variants" in sql:
                    self.inserts += 1
                    if self.inserts == 2:
                        raise RuntimeError("injected failure")
                if parameters is None:
                    return self.real.execute(sql)
                return self.real.execute(sql, parameters)

        faulty = BronzeEventStore(cast(duckdb.DuckDBPyConnection, FailingConnection(conn)))
        with pytest.raises(RuntimeError, match="injected"):
            faulty.append_batch(
                (event(), replace(event(), source_record_id="receipt-2")),
                batch_key="batch-1",
                input_artifact=b"input",
                job_id="job-1",
            )
        for name in ("event_variants", "ingest_batches", "input_artifacts"):
            row = conn.execute(
                f"SELECT count(*) FROM {qualified_bronze_name(conn, name)}"
            ).fetchone()
            assert row is not None and row[0] == 0
    finally:
        conn.close()
