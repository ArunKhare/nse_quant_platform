"""Actual evidence-snapshots SQL seed -> Bronze -> persisted Silver chain."""

from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from nse_quant.data_platform import legacy_evidence_snapshot_bronze as bronze_api
from nse_quant.data_platform import legacy_evidence_snapshots_silver_store as silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, 9, 20, tzinfo=UTC)
REVISION = "a" * 40

INSERT = """
    INSERT INTO main.evidence_snapshots VALUES (
        ?, ?, ?, ?, ?
    )
"""


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        legacy.conn.execute(
            INSERT,
            [
                "run-1",
                AT,
                "NIFTY",
                "iv_surface",
                '{"surface":"flat"}',
            ],
        )
        legacy.conn.execute(
            INSERT,
            [
                "run-1",
                AT + timedelta(seconds=1),
                None,
                "iv_surface",
                "null",
            ],
        )
        legacy.conn.execute(
            INSERT,
            [
                "run-2",
                AT,
                "BANKNIFTY",
                "gamma",
                None,
            ],
        )
    finally:
        legacy.close()


def bronze(tmp_path):
    legacy_path, bronze_path = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy_path)
    with (
        duckdb.connect(str(legacy_path), read_only=True) as source,
        duckdb.connect(str(bronze_path)) as target,
    ):
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_evidence_snapshots(source, source_label="fixture")
        result = bronze_api.preserve_evidence_snapshots(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver.EvidenceSnapshotBronzePins(
        source_label=result["source_label"],
        snapshot_id=result["snapshot_id"],
        capture_event_id=result["capture_event_id"],
        envelope_hash=result["envelope_hash"],
        recording_fingerprint=result["recording_fingerprint"],
    )


def chain(tmp_path):
    bronze_path, pins = bronze(tmp_path)
    silver_path = tmp_path / "silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_evidence_snapshots_silver(target)
        context = silver.observe_evidence_snapshots_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_evidence_snapshots_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_evidence_snapshots_bronze_to_silver_chain(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_evidence_snapshots_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 3
        assert records == bronze_api.read_evidence_snapshot_bronze(
            bronze_conn, **pins.reader_args()
        )
        assert records == silver.revalidate_evidence_snapshots_silver(
            bronze_conn,
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
            source_label=pins.source_label,
            snapshot_id=pins.snapshot_id,
            capture_event_id=pins.capture_event_id,
            envelope_hash=pins.envelope_hash,
            expected_bronze_recording_fingerprint=pins.recording_fingerprint,
        )
        rows = reader.execute(
            "SELECT run_id,ts,symbol,plugin_name,payload_json "
            "FROM silver.silver.evidence_snapshot_observations "
            "WHERE revision_id=? ORDER BY ordinal",
            [receipt["revision_id"]],
        ).fetchall()
        assert rows[0][0] == "run-1" and rows[0][1] == AT
        assert rows[0][2] == "NIFTY" and rows[0][3] == "iv_surface"
        assert rows[0][4] == '{"surface":"flat"}'
        assert rows[1][2] is None and rows[1][4] == "null"
        assert rows[2][4] is None


def test_evidence_snapshots_silver_tampering(tmp_path):
    _b, silver_path, _pins, receipt = chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.silver.evidence_snapshot_sets SET context='bad'::BLOB")
    with duckdb.connect(str(silver_path), read_only=True) as reader, pytest.raises(ValueError):
        silver.read_evidence_snapshots_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_evidence_snapshots_silver_first_write_obligation(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_evidence_snapshots_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_evidence_snapshots_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_evidence_snapshots_silver_same_file_alias(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True),
        duckdb.connect(str(silver_path)) as target,
    ):
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_evidence_snapshots_silver(
                    alias,
                    target,
                    pins=pins,
                    expected_context_sha256="a" * 64,
                    actor_id="synthetic",
                    code_revision=REVISION,
                )
            assert target.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()
