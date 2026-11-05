"""Actual underlying-IV Bronze -> persisted Silver chain."""

from datetime import UTC, date, datetime

import duckdb
import pytest

from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform import legacy_underlying_iv_observations_bronze as bronze_api
from nse_quant.data_platform import legacy_underlying_iv_observations_silver as silver
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
EXPIRY = date(2026, 1, 29)
REVISION = "a" * 40


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        table = bronze_api.common.name(legacy.conn, "main", bronze_api.codec.TABLE)
        legacy.conn.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?)",
            [AT, "NIFTY", EXPIRY, 0.15, 24500.5, "atm_average_live"],
        )
        legacy.conn.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?)",
            [AT, "BANKNIFTY", EXPIRY, 0.18, None, "atm_average_live"],
        )
    finally:
        legacy.close()


def create_bronze(tmp_path):
    legacy, bronze_path = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze_path)) as b,
    ):
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = bronze_api.capture_underlying_iv_observations(source, source_label="fixture")
        result = bronze_api.preserve_underlying_iv_observations(
            source,
            b,
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
    bronze_path, pins = create_bronze(tmp_path)
    silver_path = tmp_path / "underlying_iv_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_reader,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_underlying_iv_observations_silver(target)
        context = silver.observe_underlying_iv_observations_bronze(bronze_reader, pins=pins)
        receipt = silver.persist_underlying_iv_observations_silver(
            bronze_reader,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_underlying_iv_bronze_to_silver_chain(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_underlying_iv_observations_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 2
        assert records == bronze_api.read_underlying_iv_observations_bronze(
            bronze, **pins.reader_args()
        )
        assert records == silver.revalidate_underlying_iv_observations_silver(
            bronze,
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
            source_label=pins.source_label,
            snapshot_id=pins.snapshot_id,
            capture_event_id=pins.capture_event_id,
            envelope_hash=pins.envelope_hash,
            recording_fingerprint=pins.recording_fingerprint,
        )


@pytest.mark.parametrize(
    "kind", ["context", "records", "audit", "clock"], ids=["context", "records", "audit", "clock"]
)
def test_underlying_iv_silver_tampering(tmp_path, kind):
    _b, silver_path, _pins, receipt = chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        if kind == "context":
            writer.execute("UPDATE silver.underlying_iv_observation_sets SET context='bad'::BLOB")
        elif kind == "records":
            writer.execute(
                "UPDATE silver.underlying_iv_observation_records SET record_bytes='bad'::BLOB"
            )
        elif kind == "audit":
            writer.execute("DELETE FROM medallion_audit.job_events WHERE state='SUCCEEDED'")
        else:
            writer.execute(
                "UPDATE silver.underlying_iv_observation_sets "
                "SET recorded_at=recorded_at+INTERVAL '1 second'"
            )
    with duckdb.connect(str(silver_path), read_only=True) as reader, pytest.raises(ValueError):
        silver.read_underlying_iv_observations_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_silver_first_write_original_obligation(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_underlying_iv_observations_bronze(bronze, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_underlying_iv_observations_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_same_file_alias_separate_target(tmp_path):
    _bronze_path, silver_path, pins, _receipt = chain(tmp_path)
    with duckdb.connect(str(silver_path)) as target:
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_underlying_iv_observations_silver(
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
