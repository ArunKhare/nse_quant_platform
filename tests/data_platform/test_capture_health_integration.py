"""Local integration using actual FS1b journal, A1 ledger and review publication."""

import hashlib
import json
from datetime import UTC, datetime

import duckdb

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.capture_health import inspect_capture
from nse_quant.data_platform.capture_health_cli import main
from nse_quant.data_platform.native_kite_capture import RawFrameJournal, file_hash


def test_native_session_inspection_and_audited_review_export(tmp_path):
    source = tmp_path / "session"
    journal = RawFrameJournal(source, "session-1")
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
            journal.append(
                b"original",
                received_at=datetime(2026, 10, 30, tzinfo=UTC),
                payload_format="kite_ws_binary_payload",
            )
            journal.close(clean=True, audit_job_id=job)
    finally:
        conn.close()
    before = {path.name: file_hash(path) for path in source.iterdir() if path.is_file()}
    assert inspect_capture(source).automatic_ingestion_allowed
    output = tmp_path / "reviews"
    assert (
        main(
            [
                "--session-dir",
                str(source),
                "--publish-plan",
                "--output-root",
                str(output),
                "--code-revision",
                "qa-commit",
            ]
        )
        == 0
    )
    after = {path.name: file_hash(path) for path in source.iterdir() if path.is_file()}
    assert before == after
    directories = list(output.iterdir())
    assert len(directories) == 1
    plan = json.loads((directories[0] / "recovery_plan.json").read_text())
    assert plan["automatic_repair_allowed"] is False
    conn = duckdb.connect(str(directories[0] / "inspection_audit.duckdb"), read_only=True)
    try:
        state = conn.execute(
            "SELECT state FROM medallion_audit.job_events ORDER BY event_index DESC LIMIT 1"
        ).fetchone()
        assert state is not None and state[0] == "SUCCEEDED"
    finally:
        conn.close()
