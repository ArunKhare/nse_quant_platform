"""Actual daily-RV Silver -> persisted Gold chain."""

from datetime import UTC, date, datetime

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv_gold as gold
from nse_quant.data_platform import legacy_daily_rv_observations_bronze as bronze_api
from nse_quant.data_platform import legacy_daily_rv_observations_silver as silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
DAY = date(2026, 1, 1)
REVISION = "a" * 40


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        table = bronze_api.common.name(legacy.conn, "main", bronze_api.codec.TABLE)
        legacy.conn.execute(f"INSERT INTO {table} VALUES (?,?,?,?)", ["NIFTY", DAY, 0.12, 375])
        legacy.conn.execute(f"INSERT INTO {table} VALUES (?,?,?,?)", ["BANKNIFTY", DAY, 0.18, 400])
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
        snapshot = bronze_api.capture_daily_rv_observations(source, source_label="fixture")
        result = bronze_api.preserve_daily_rv_observations(
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
    silver_path = tmp_path / "daily_rv_silver.duckdb"
    gold_path = tmp_path / "daily_rv_gold.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as silver_target,
    ):
        silver.initialize_daily_rv_silver(silver_target)
        context = silver.observe_daily_rv_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_daily_rv_silver(
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
        gold.initialize_daily_rv_gold(gold_target)
        context = gold.observe_daily_rv_silver(
            silver_reader,
            pins=pins,
            revision_id=receipt["revision_id"],
            expected_silver_recording_fingerprint=receipt["recording_fingerprint"],
        )
        gold_receipt = gold.persist_daily_rv_gold(
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


def test_daily_rv_silver_to_gold_chain(tmp_path):
    silver_path, gold_path, pins, silver_receipt, gold_receipt = chain(tmp_path)
    with (
        duckdb.connect(str(silver_path), read_only=True) as silver_reader,
        duckdb.connect(str(gold_path), read_only=True) as gold_reader,
    ):
        records = gold.read_daily_rv_gold(
            gold_reader,
            revision_id=gold_receipt["revision_id"],
            expected_recording_fingerprint=gold_receipt["recording_fingerprint"],
        )
        assert len(records) == gold_receipt["row_count"] == 2
        assert records == silver.read_daily_rv_silver(
            silver_reader,
            revision_id=silver_receipt["revision_id"],
            expected_recording_fingerprint=silver_receipt["recording_fingerprint"],
        )
        assert records == gold.revalidate_daily_rv_gold(
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
def test_daily_rv_gold_tampering(tmp_path, kind):
    _s, gold_path, _pins, _sr, gold_receipt = chain(tmp_path)
    with duckdb.connect(str(gold_path)) as writer:
        if kind == "context":
            writer.execute("UPDATE gold.daily_rv_gold_sets SET context='bad'::BLOB")
        elif kind == "records":
            writer.execute("UPDATE gold.daily_rv_gold_observations SET record_bytes='bad'::BLOB")
        elif kind == "audit":
            writer.execute("DELETE FROM medallion_audit.job_events WHERE state='SUCCEEDED'")
        else:
            writer.execute(
                "UPDATE gold.daily_rv_gold_sets SET recorded_at=recorded_at+INTERVAL '1 second'"
            )
    with duckdb.connect(str(gold_path), read_only=True) as reader, pytest.raises(ValueError):
        gold.read_daily_rv_gold(
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
        context = gold.observe_daily_rv_silver(
            silver_reader,
            pins=pins,
            revision_id=silver_receipt["revision_id"],
            expected_silver_recording_fingerprint=silver_receipt["recording_fingerprint"],
        )
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            gold.persist_daily_rv_gold(
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
    _silver_path, gold_path, pins, silver_receipt, _gr = chain(tmp_path)
    with duckdb.connect(str(gold_path)) as target:
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                gold.persist_daily_rv_gold(
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
