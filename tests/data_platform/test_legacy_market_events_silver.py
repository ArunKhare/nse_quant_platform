"""Actual market-events writer -> Bronze -> persisted Silver chain."""

from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import legacy_market_events_bronze as bronze_api
from nse_quant.data_platform import legacy_market_events_silver_store as silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
REVISION = "a" * 40


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        legacy.conn.executemany(
            "INSERT INTO market_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                [
                    "event-1",
                    "synthetic",
                    "ECONOMIC",
                    "CPI release",
                    "Monthly CPI",
                    "NIFTY",
                    AT,
                    "HIGH",
                    5.0,
                    5.5,
                    "ABOVE",
                    '["NIFTY"]',
                    '{"cpi":5.5}',
                    AT,
                ],
                [
                    "event-2",
                    "synthetic",
                    "ECONOMIC",
                    "RBI policy",
                    "Repo rate",
                    None,
                    AT,
                    "MEDIUM",
                    None,
                    None,
                    None,
                    "null",
                    None,
                    AT,
                ],
                [
                    "event-3",
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
                ],
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
        snapshot = bronze_api.capture_market_events(source, source_label="fixture")
        result = bronze_api.preserve_market_events(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver.MarketEventsBronzePins(
        source_label=result["source_label"],
        snapshot_id=result["snapshot_id"],
        capture_event_id=result["capture_event_id"],
        envelope_hash=result["envelope_hash"],
        recording_fingerprint=result["recording_fingerprint"],
    )


def chain(tmp_path):
    bronze_path, pins = bronze(tmp_path)
    silver_path = tmp_path / "market_events_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_market_events_silver(target)
        context = silver.observe_market_events_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_market_events_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_market_events_bronze_to_silver_chain(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_market_events_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 3
        assert records == bronze_api.read_market_events_bronze(bronze_conn, **pins.reader_args())
        assert records == silver.revalidate_market_events_silver(
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
            "SELECT event_id,source,event_type,title,description,symbol,event_ts,"
            "importance,consensus_value,actual_value,surprise_label,"
            "affected_underlyings,raw_payload,ingested_at "
            "FROM silver.market_event_observations WHERE revision_id=? ORDER BY ordinal",
            [receipt["revision_id"]],
        ).fetchall()
        assert rows[0][0] == "event-1" and rows[0][6] == AT
        assert rows[0][8] == 5.0 and rows[0][9] == 5.5
        assert rows[0][11] == '["NIFTY"]' and rows[0][12] == '{"cpi":5.5}'
        assert rows[1][5] is None and rows[1][11] == "null" and rows[1][12] is None
        assert rows[2][1:] == (None,) * 13


def test_market_events_silver_tampering(tmp_path):
    _b, silver_path, _pins, receipt = chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.market_event_sets SET context='bad'::BLOB")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError),
    ):
        silver.read_market_events_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_market_events_silver_first_write_obligation(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_market_events_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_market_events_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_market_events_silver_same_file_alias(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True),
        duckdb.connect(str(silver_path)) as target,
    ):
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_market_events_silver(
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
