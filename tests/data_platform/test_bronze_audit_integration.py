"""Local integration with A1/A2 and unambiguous file-backed Bronze queries."""

import base64
import json

import duckdb

from nse_quant.data_platform.bronze import qualified_bronze_name
from nse_quant.data_platform.bronze_import import main


def test_audited_import_and_exact_retry(tmp_path):
    source = tmp_path / "events.jsonl"
    source.write_text(
        json.dumps(
            {
                "envelope_version": 1,
                "source": "fixture",
                "capture_session_id": "session-1",
                "source_record_id": "receipt-1",
                "received_at": "2026-10-30T09:15:00+00:00",
                "payload_base64": base64.b64encode(b"original").decode(),
                "payload_format": "binary",
                "origin_kind": "historical_import",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    database = tmp_path / "bronze.duckdb"
    arguments = [
        "--input",
        str(source),
        "--bronze-db",
        str(database),
        "--manifest-root",
        str(tmp_path / "manifests"),
        "--batch-key",
        "batch-1",
        "--execute",
        "--initialize",
        "--code-revision",
        "qa-commit",
    ]
    assert main(arguments) == 0
    assert main(arguments) == 0
    conn = duckdb.connect(str(database), read_only=True)
    try:
        variants = conn.execute(
            f"SELECT count(*) FROM {qualified_bronze_name(conn, 'event_variants')}"
        ).fetchone()
        batches = conn.execute(
            f"SELECT count(*) FROM {qualified_bronze_name(conn, 'ingest_batches')}"
        ).fetchone()
        successes = conn.execute(
            "SELECT count(*) FROM medallion_audit.job_events WHERE state='SUCCEEDED'"
        ).fetchone()
        assert variants is not None and variants[0] == 1
        assert batches is not None and batches[0] == 1
        assert successes is not None and successes[0] == 2
    finally:
        conn.close()
