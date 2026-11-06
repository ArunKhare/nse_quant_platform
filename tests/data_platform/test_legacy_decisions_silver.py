"""Actual decisions SQL seed -> Bronze -> persisted Silver chain."""

from datetime import UTC, date, datetime

import duckdb
import pytest

from nse_quant.data_platform import legacy_decisions_bronze as bronze_api
from nse_quant.data_platform import legacy_decisions_silver_store as silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, 9, 20, tzinfo=UTC)
EXPIRY = date(2026, 1, 29)
REVISION = "a" * 40

INSERT = """
    INSERT INTO main.decisions VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?, ?
    )
"""


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        legacy.conn.execute(
            INSERT,
            [
                "decision-1",
                AT,
                "run-1",
                "ENTRY",
                "prop-1",
                "strat-1",
                "NIFTY",
                EXPIRY,
                '{"action":"enter"}',
            ],
        )
        legacy.conn.execute(
            INSERT,
            [
                "decision-2",
                AT,
                "run-1",
                "HOLD",
                "prop-1",
                "strat-1",
                "NIFTY",
                EXPIRY,
                "null",
            ],
        )
        legacy.conn.execute(
            INSERT,
            [
                "decision-3",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
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
        snapshot = bronze_api.capture_decisions(source, source_label="fixture")
        result = bronze_api.preserve_decisions(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver.DecisionsBronzePins(
        source_label=result["source_label"],
        snapshot_id=result["snapshot_id"],
        capture_event_id=result["capture_event_id"],
        envelope_hash=result["envelope_hash"],
        recording_fingerprint=result["recording_fingerprint"],
    )


def chain(tmp_path):
    bronze_path, pins = bronze(tmp_path)
    silver_path = tmp_path / "decisions_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_decisions_silver(target)
        context = silver.observe_decisions_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_decisions_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_decisions_bronze_to_silver_chain(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_decisions_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 3
        assert records == bronze_api.read_decisions_bronze(bronze_conn, **pins.reader_args())
        assert records == silver.revalidate_decisions_silver(
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
            "SELECT decision_id,ts,run_id,decision_type,proposal_id,strategy,"
            "underlying,expiry,payload "
            "FROM silver.decision_observations WHERE revision_id=? ORDER BY ordinal",
            [receipt["revision_id"]],
        ).fetchall()
        assert rows[0][0] == "decision-1" and rows[0][1] == AT
        assert rows[0][3] == "ENTRY" and rows[0][7] == EXPIRY
        assert rows[0][8] == '{"action":"enter"}'
        assert rows[1][3] == "HOLD" and rows[1][8] == "null"
        assert rows[2][1:] == (None,) * 8


def test_decisions_silver_tampering(tmp_path):
    _b, silver_path, _pins, receipt = chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.decision_sets SET context='bad'::BLOB")
    with duckdb.connect(str(silver_path), read_only=True) as reader, pytest.raises(ValueError):
        silver.read_decisions_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_decisions_silver_first_write_obligation(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_decisions_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_decisions_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_decisions_silver_same_file_alias(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True),
        duckdb.connect(str(silver_path)) as target,
    ):
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_decisions_silver(
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
