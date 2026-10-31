"""Local integration: sealed session -> audited Bronze import -> exact replay retry."""

import hashlib
from datetime import UTC, datetime

import duckdb

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import qualified_bronze_name
from nse_quant.data_platform.drain_capture import main
from nse_quant.data_platform.native_kite_capture import RawFrameJournal, file_hash


def test_audited_capture_segments_drain_without_duplicates(tmp_path):
    source = tmp_path / "session"
    journal = RawFrameJournal(source, "session-1", max_segment_records=1)
    conn = duckdb.connect(str(source / "audit.duckdb"))
    try:
        ledger = AuditLedger(conn)
        ledger.initialize()
        job = ledger.plan_job(
            command_name="capture.kite_raw@1",
            actor_id="qa",
            scope_ref="fixture",
            code_revision="qa-commit",
            config_hash=hashlib.sha256(b"fixture").hexdigest(),
        )
        with ledger.execution(job):
            for payload in (b"first", b"second"):
                journal.append(
                    payload,
                    received_at=datetime(2026, 10, 30, tzinfo=UTC),
                    payload_format="kite_ws_binary_payload",
                )
            journal.close(clean=True, audit_job_id=job)
    finally:
        conn.close()
    before = file_hash(source / "audit.duckdb")
    target = tmp_path / "bronze.duckdb"
    arguments = [
        "--session-dir",
        str(source),
        "--bronze-db",
        str(target),
        "--manifest-root",
        str(tmp_path / "manifests"),
        "--execute",
        "--initialize",
        "--code-revision",
        "qa-commit",
    ]
    assert main(arguments) == 0
    assert main(arguments) == 0
    assert file_hash(source / "audit.duckdb") == before
    conn = duckdb.connect(str(target), read_only=True)
    try:
        variants = qualified_bronze_name(conn, "event_variants")
        row = conn.execute(f"SELECT count(*) FROM {variants}").fetchone()
        assert row is not None and row[0] == 2
        payloads = conn.execute(
            f"SELECT payload FROM {variants} ORDER BY ingest_sequence"
        ).fetchall()
        assert [bytes(item[0]) for item in payloads] == [b"first", b"second"]
    finally:
        conn.close()
