"""Actual Bronze -> persisted Silver chain for spot candles and daily RV."""

from datetime import UTC, date, datetime

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv_observations_bronze as rv_bronze
from nse_quant.data_platform import legacy_daily_rv_observations_silver as rv_silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform import legacy_spot_candles_bronze as candle_bronze
from nse_quant.data_platform import legacy_spot_candles_silver as candle_silver
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
DAY = date(2026, 1, 1)
REVISION = "a" * 40


def seed_candles(path):
    legacy = DuckDBStore(path=path)
    try:
        legacy.write_spot_candles(
            [
                dict(
                    date=AT,
                    open=100.0,
                    high=110.0,
                    low=95.0,
                    close=105.0,
                    volume=1000,
                )
            ],
            "NIFTY",
            12345,
            "minute",
        )
        legacy.write_spot_candles(
            [
                dict(
                    date=AT,
                    open=200.0,
                    high=220.0,
                    low=190.0,
                    close=210.0,
                    volume=2000,
                )
            ],
            "BANKNIFTY",
            67890,
            "minute",
        )
    finally:
        legacy.close()


def seed_rv(path):
    legacy = DuckDBStore(path=path)
    try:
        table = rv_bronze.common.name(legacy.conn, "main", rv_bronze.codec.TABLE)
        legacy.conn.execute(f"INSERT INTO {table} VALUES (?,?,?,?)", ["NIFTY", DAY, 0.12, 375])
        legacy.conn.execute(f"INSERT INTO {table} VALUES (?,?,?,?)", ["BANKNIFTY", DAY, 0.18, 400])
    finally:
        legacy.close()


def bronze_candles(tmp_path):
    legacy, bronze = tmp_path / "candles.duckdb", tmp_path / "candles_bronze.duckdb"
    seed_candles(legacy)
    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = candle_bronze.capture_spot_candles(source, source_label="fixture")
        result = candle_bronze.preserve_spot_candles(
            source,
            b,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze, base.SilverPins(
        source_label=result["source_label"],
        snapshot_id=result["snapshot_id"],
        capture_event_id=result["capture_event_id"],
        envelope_hash=result["envelope_hash"],
        recording_fingerprint=result["recording_fingerprint"],
    )


def bronze_rv(tmp_path):
    legacy, bronze = tmp_path / "rv.duckdb", tmp_path / "rv_bronze.duckdb"
    seed_rv(legacy)
    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = rv_bronze.capture_daily_rv_observations(source, source_label="fixture")
        result = rv_bronze.preserve_daily_rv_observations(
            source,
            b,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze, base.SilverPins(
        source_label=result["source_label"],
        snapshot_id=result["snapshot_id"],
        capture_event_id=result["capture_event_id"],
        envelope_hash=result["envelope_hash"],
        recording_fingerprint=result["recording_fingerprint"],
    )


def chain_candles(tmp_path):
    bronze_path, pins = bronze_candles(tmp_path)
    silver_path = tmp_path / "candles_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(silver_path)) as target,
    ):
        candle_silver.initialize_spot_candles_silver(target)
        context = candle_silver.observe_spot_candles_bronze(bronze, pins=pins)
        receipt = candle_silver.persist_spot_candles_silver(
            bronze,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def chain_rv(tmp_path):
    bronze_path, pins = bronze_rv(tmp_path)
    silver_path = tmp_path / "rv_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(silver_path)) as target,
    ):
        rv_silver.initialize_daily_rv_silver(target)
        context = rv_silver.observe_daily_rv_bronze(bronze, pins=pins)
        receipt = rv_silver.persist_daily_rv_silver(
            bronze,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_spot_candles_bronze_to_silver_chain(tmp_path):
    bronze_path, silver_path, pins, receipt = chain_candles(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = candle_silver.read_spot_candles_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 2
        assert records == candle_bronze.read_spot_candles_bronze(bronze, **pins.reader_args())
        assert records == candle_silver.revalidate_spot_candles_silver(
            bronze,
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
            **pins.reader_args(),
        )


def test_daily_rv_bronze_to_silver_chain(tmp_path):
    bronze_path, silver_path, pins, receipt = chain_rv(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = rv_silver.read_daily_rv_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 2
        assert records == rv_bronze.read_daily_rv_observations_bronze(bronze, **pins.reader_args())
        assert records == rv_silver.revalidate_daily_rv_silver(
            bronze,
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
            **pins.reader_args(),
        )


@pytest.mark.parametrize(
    "kind", ["context", "records", "audit", "clock"], ids=["context", "records", "audit", "clock"]
)
def test_spot_candles_silver_tampering(tmp_path, kind):
    _b, silver_path, _pins, receipt = chain_candles(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        if kind == "context":
            writer.execute("UPDATE silver.spot_candle_sets SET context='bad'::BLOB")
        elif kind == "records":
            writer.execute("UPDATE silver.spot_candle_observations SET record_bytes='bad'::BLOB")
        elif kind == "audit":
            writer.execute("DELETE FROM medallion_audit.job_events WHERE state='SUCCEEDED'")
        else:
            writer.execute(
                "UPDATE silver.spot_candle_sets SET recorded_at=recorded_at+INTERVAL '1 second'"
            )
    with duckdb.connect(str(silver_path), read_only=True) as reader, pytest.raises(ValueError):
        candle_silver.read_spot_candles_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


@pytest.mark.parametrize(
    "kind", ["context", "records", "audit", "clock"], ids=["context", "records", "audit", "clock"]
)
def test_daily_rv_silver_tampering(tmp_path, kind):
    _b, silver_path, _pins, receipt = chain_rv(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        if kind == "context":
            writer.execute("UPDATE silver.daily_rv_sets SET context='bad'::BLOB")
        elif kind == "records":
            writer.execute("UPDATE silver.daily_rv_observations SET record_bytes='bad'::BLOB")
        elif kind == "audit":
            writer.execute("DELETE FROM medallion_audit.job_events WHERE state='SUCCEEDED'")
        else:
            writer.execute(
                "UPDATE silver.daily_rv_sets SET recorded_at=recorded_at+INTERVAL '1 second'"
            )
    with duckdb.connect(str(silver_path), read_only=True) as reader, pytest.raises(ValueError):
        rv_silver.read_daily_rv_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_silver_first_write_original_obligation(tmp_path):
    bronze_path, silver_path, pins, receipt = chain_candles(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = candle_silver.observe_spot_candles_bronze(bronze, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            candle_silver.persist_spot_candles_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_rv_silver_first_write_original_obligation(tmp_path):
    bronze_path, silver_path, pins, receipt = chain_rv(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = rv_silver.observe_daily_rv_bronze(bronze, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            rv_silver.persist_daily_rv_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_same_file_alias_separate_target(tmp_path):
    _bronze_path, silver_path, pins, _receipt = chain_candles(tmp_path)
    with duckdb.connect(str(silver_path)) as target:
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                candle_silver.persist_spot_candles_silver(
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
