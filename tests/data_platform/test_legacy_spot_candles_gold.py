"""Actual spot-candles Silver -> persisted Gold chain."""

from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform import legacy_spot_candles_bronze as bronze_api
from nse_quant.data_platform import legacy_spot_candles_gold as gold
from nse_quant.data_platform import legacy_spot_candles_silver as silver
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
REVISION = "a" * 40


def seed(path):
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


def bronze(tmp_path):
    legacy_path, bronze_path = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy_path)
    with (
        duckdb.connect(str(legacy_path), read_only=True) as source,
        duckdb.connect(str(bronze_path)) as target,
    ):
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_spot_candles(source, source_label="fixture")
        result = bronze_api.preserve_spot_candles(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, base.SilverPins(
        source_label=result["source_label"],
        snapshot_id=result["snapshot_id"],
        capture_event_id=result["capture_event_id"],
        envelope_hash=result["envelope_hash"],
        recording_fingerprint=result["recording_fingerprint"],
    )


def chain(tmp_path):
    bronze_path, pins = bronze(tmp_path)
    silver_path = tmp_path / "spot_candles_silver.duckdb"
    gold_path = tmp_path / "spot_candles_gold.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as silver_target,
    ):
        silver.initialize_spot_candles_silver(silver_target)
        context = silver.observe_spot_candles_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_spot_candles_silver(
            bronze_conn,
            silver_target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    with (
        duckdb.connect(str(silver_path), read_only=True) as silver_reader,
        duckdb.connect(str(gold_path)) as gold_target,
    ):
        gold.initialize_spot_candles_gold(gold_target)
        context = gold.observe_spot_candles_silver(
            silver_reader,
            pins=pins,
            revision_id=receipt["revision_id"],
            expected_silver_recording_fingerprint=receipt["recording_fingerprint"],
        )
        gold_receipt = gold.persist_spot_candles_gold(
            silver_reader,
            gold_target,
            pins=pins,
            silver_revision_id=receipt["revision_id"],
            expected_silver_recording_fingerprint=receipt["recording_fingerprint"],
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return silver_path, gold_path, pins, receipt, gold_receipt


def test_spot_candles_silver_to_gold_chain(tmp_path):
    silver_path, gold_path, pins, silver_receipt, gold_receipt = chain(tmp_path)
    with (
        duckdb.connect(str(silver_path), read_only=True) as silver_reader,
        duckdb.connect(str(gold_path), read_only=True) as gold_reader,
    ):
        records = gold.read_spot_candles_gold(
            gold_reader,
            revision_id=gold_receipt["revision_id"],
            expected_recording_fingerprint=gold_receipt["recording_fingerprint"],
        )
        assert len(records) == gold_receipt["row_count"] == 2
        assert records == silver.read_spot_candles_silver(
            silver_reader,
            revision_id=silver_receipt["revision_id"],
            expected_recording_fingerprint=silver_receipt["recording_fingerprint"],
        )
        assert records == gold.revalidate_spot_candles_gold(
            silver_reader,
            gold_reader,
            revision_id=gold_receipt["revision_id"],
            expected_recording_fingerprint=gold_receipt["recording_fingerprint"],
            silver_revision_id=silver_receipt["revision_id"],
            expected_silver_recording_fingerprint=silver_receipt["recording_fingerprint"],
            source_label=pins.source_label,
            snapshot_id=pins.snapshot_id,
            capture_event_id=pins.capture_event_id,
            envelope_hash=pins.envelope_hash,
            recording_fingerprint=pins.recording_fingerprint,
        )


@pytest.mark.parametrize(
    "kind", ["context", "records", "audit", "clock"], ids=["context", "records", "audit", "clock"]
)
def test_spot_candles_gold_tampering(tmp_path, kind):
    _s, gold_path, _pins, _sr, gold_receipt = chain(tmp_path)
    with duckdb.connect(str(gold_path)) as writer:
        if kind == "context":
            writer.execute("UPDATE gold.spot_candle_gold_sets SET context='bad'::BLOB")
        elif kind == "records":
            writer.execute("UPDATE gold.spot_candle_gold_observations SET record_bytes='bad'::BLOB")
        elif kind == "audit":
            writer.execute("DELETE FROM medallion_audit.job_events WHERE state='SUCCEEDED'")
        else:
            writer.execute(
                "UPDATE gold.spot_candle_gold_sets SET recorded_at=recorded_at+INTERVAL '1 second'"
            )
    with duckdb.connect(str(gold_path), read_only=True) as reader, pytest.raises(ValueError):
        gold.read_spot_candles_gold(
            reader,
            revision_id=gold_receipt["revision_id"],
            expected_recording_fingerprint=gold_receipt["recording_fingerprint"],
        )


def test_gold_first_write_original_obligation(tmp_path):
    silver_path, gold_path, pins, silver_receipt, _gr = chain(tmp_path)
    with (
        duckdb.connect(str(silver_path), read_only=True) as silver_reader,
        duckdb.connect(str(gold_path)) as target,
    ):
        context = gold.observe_spot_candles_silver(
            silver_reader,
            pins=pins,
            revision_id=silver_receipt["revision_id"],
            expected_silver_recording_fingerprint=silver_receipt["recording_fingerprint"],
        )
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            gold.persist_spot_candles_gold(
                silver_reader,
                target,
                pins=pins,
                silver_revision_id=silver_receipt["revision_id"],
                expected_silver_recording_fingerprint=silver_receipt["recording_fingerprint"],
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_same_file_alias_separate_target(tmp_path):
    silver_path, gold_path, pins, silver_receipt, _gr = chain(tmp_path)
    with duckdb.connect(str(gold_path)) as target:
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                gold.persist_spot_candles_gold(
                    alias,
                    target,
                    pins=pins,
                    silver_revision_id=silver_receipt["revision_id"],
                    expected_silver_recording_fingerprint=silver_receipt["recording_fingerprint"],
                    expected_context_sha256="a" * 64,
                    actor_id="synthetic",
                    code_revision=REVISION,
                )
            assert target.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()
