"""Actual feature-snapshots SQL seed -> Bronze -> persisted Silver chain."""

from datetime import UTC, date, datetime

import duckdb
import pytest

from nse_quant.data_platform import legacy_feature_snapshot_bronze as bronze_api
from nse_quant.data_platform import legacy_feature_snapshots_silver_store as silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, 9, 20, tzinfo=UTC)
EXPIRY = date(2026, 1, 29)
REVISION = "a" * 40

INSERT = """
    INSERT INTO main.feature_snapshots VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
    )
"""


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        legacy.conn.execute(
            INSERT,
            [
                "feature-1",
                AT,
                "run-1",
                "NIFTY",
                EXPIRY,
                25000.0,
                12.5,
                40.0,
                55.0,
                11.0,
                1.5,
                1.2,
                100000,
                90000,
                25000.0,
                80.0,
                "RISK_ON",
                0.5,
                180.0,
                1.1,
                275.0,
                '{"note":"ok"}',
            ],
        )
        legacy.conn.execute(
            INSERT,
            [
                "feature-2",
                AT,
                "run-1",
                "NIFTY",
                EXPIRY,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "null",
            ],
        )
        legacy.conn.execute(
            INSERT,
            [
                "feature-3",
                AT,
                "run-2",
                "BANKNIFTY",
                EXPIRY,
                52000.0,
                14.0,
                35.0,
                60.0,
                12.0,
                2.0,
                1.1,
                120000,
                110000,
                52000.0,
                85.0,
                "RISK_ON",
                0.6,
                200.0,
                1.2,
                300.0,
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
        snapshot = bronze_api.capture_feature_snapshots(source, source_label="fixture")
        result = bronze_api.preserve_feature_snapshots(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver.FeatureSnapshotBronzePins(
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
        silver.initialize_feature_snapshots_silver(target)
        context = silver.observe_feature_snapshots_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_feature_snapshots_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_feature_snapshots_bronze_to_silver_chain(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_feature_snapshots_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 3
        assert records == bronze_api.read_feature_snapshot_bronze(bronze_conn, **pins.reader_args())
        assert records == silver.revalidate_feature_snapshots_silver(
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
            "SELECT feature_id,ts,run_id,underlying,expiry,spot,atm_iv,"
            "total_call_oi,regime,short_momentum,diagnostics "
            "FROM silver.silver.feature_snapshot_observations WHERE revision_id=? ORDER BY ordinal",
            [receipt["revision_id"]],
        ).fetchall()
        assert rows[0][0] == "feature-1" and rows[0][1] == AT
        assert rows[0][4] == EXPIRY and rows[0][5] == 25000.0
        assert rows[0][7] == 100000 and rows[0][8] == "RISK_ON"
        assert rows[0][9] == 0.5 and rows[0][10] == '{"note":"ok"}'
        assert rows[1][5:10] == (None,) * 5
        assert rows[1][10] == "null"
        assert rows[2][10] is None


def test_feature_snapshots_silver_tampering(tmp_path):
    _b, silver_path, _pins, receipt = chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.silver.feature_snapshot_sets SET context='bad'::BLOB")
    with duckdb.connect(str(silver_path), read_only=True) as reader, pytest.raises(ValueError):
        silver.read_feature_snapshots_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_feature_snapshots_silver_first_write_obligation(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_feature_snapshots_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_feature_snapshots_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_feature_snapshots_silver_same_file_alias(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True),
        duckdb.connect(str(silver_path)) as target,
    ):
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_feature_snapshots_silver(
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
