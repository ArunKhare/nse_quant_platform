"""Actual spot-feature writer -> native Bronze; no feature truth or admission."""

from datetime import UTC, datetime, timedelta

import duckdb
import pandas as pd
import pytest

from nse_quant.data_platform import legacy_spot_features as codec
from nse_quant.data_platform import legacy_spot_features_bronze as native
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
IMPORT_AT = datetime(2026, 1, 2, tzinfo=UTC)
REVISION = "a" * 40


def frame():
    return pd.DataFrame(
        [
            dict(
                symbol="NIFTY",
                ts=AT,
                close=100.5,
                return_1m=0.001,
                rv_1m_30=0.12,
                atr_1m_14=1.25,
                vwap_1m=100.25,
                vwap_distance_1m=0.0025,
                volume_zscore_1m_30=0.75,
                trend_15m=0.5,
                atr_15m_14=2.5,
                range_position_15m=0.65,
                trend_60m=0.4,
                atr_60m_14=3.5,
                range_position_60m=0.55,
            ),
            dict(
                symbol="BANKNIFTY",
                ts=AT,
                close=500.5,
                return_1m=None,
                rv_1m_30=None,
                atr_1m_14=None,
                vwap_1m=None,
                vwap_distance_1m=None,
                volume_zscore_1m_30=None,
                trend_15m=None,
                atr_15m_14=None,
                range_position_15m=None,
                trend_60m=None,
                atr_60m_14=None,
                range_position_60m=None,
            ),
        ]
    )


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        legacy.write_spot_features(frame())
        table = native.common.name(legacy.conn, "main", codec.TABLE)
        legacy.conn.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ["NIFTY", AT + timedelta(minutes=1)] + [None] * 13,
        )
    finally:
        legacy.close()


def record(tmp_path):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_spot_features(source, source_label="fixture")
        result = native.preserve_spot_features(
            source,
            b,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=IMPORT_AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return legacy, bronze, result


def args(result):
    return dict(
        source_label=result["source_label"],
        snapshot_id=result["snapshot_id"],
        capture_event_id=result["capture_event_id"],
        envelope_hash=result["envelope_hash"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )


def read(path, result):
    with duckdb.connect(str(path), read_only=True) as connection:
        return native.read_spot_features_bronze(connection, **args(result))


def test_actual_writer_and_native_chain_retain_every_field(tmp_path):
    legacy, bronze, result = record(tmp_path)
    rows = read(bronze, result)
    assert len(rows) == result["row_count"] == 3
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze), read_only=True) as connection,
    ):
        assert native.revalidate_spot_features_source(source, connection, **args(result)) == rows
        table = native.common.name(source, "main", codec.TABLE)
        originals = source.execute(f"SELECT * FROM {table}").fetchall()
        keys = [(row[0], row[1]) for row in originals]
        assert len(set(keys)) == len(keys) == 3
        for ordinal, raw in enumerate(rows):
            document = codec.parse(raw, codec.MAX_RECORD)
            fields = document["stored_fields"]
            assert document["source_ordinal"] == ordinal
            assert (fields["symbol"], datetime.fromisoformat(fields["ts"])) in keys
            assert not document["original_feature_execution_replayed"]
            assert not document["native_decision_replayed"]
            assert not document["decision_eligibility_asserted"]
        by_key = {(row[0], row[1]): row for row in originals}
        first = by_key[("NIFTY", AT)]
        assert first[2] == 100.5 and first[3] == 0.001
        assert first[11] == 0.65 and first[14] == 0.55
        second = by_key[("BANKNIFTY", AT)]
        assert second[2] == 500.5 and all(value is None for value in second[3:])
        third = by_key[("NIFTY", AT + timedelta(minutes=1))]
        assert third[2:] == (None,) * 13


def test_retained_feature_is_not_native_feature_truth(tmp_path):
    _legacy, bronze, result = record(tmp_path)
    for raw in read(bronze, result):
        document = codec.parse(raw, codec.MAX_RECORD)
        assert document["classification"] == "RETAINED_LEGACY_SPOT_FEATURE_NOT_NATIVE_FEATURE_TRUTH"
        assert not document["feature_interpreted"]
        assert not document["trend_interpreted"]
        assert not document["volatility_interpreted"]
        assert not document["publication_asserted"]
        assert not document["decision_eligibility_asserted"]


@pytest.mark.parametrize(
    "kind",
    ["payload", "artifact", "event-id", "audit", "clock"],
    ids=["payload", "artifact", "id", "audit", "clock"],
)
def test_original_native_recording_tampering(tmp_path, kind):
    _legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(bronze)) as connection:
        variants = native.common.name(connection, "bronze", "event_variants")
        if kind == "payload":
            connection.execute(f"UPDATE {variants} SET payload='bad'::BLOB")
        elif kind == "artifact":
            table = native.common.name(connection, "bronze", "input_artifacts")
            connection.execute(f"UPDATE {table} SET artifact_bytes='bad'::BLOB")
        elif kind == "event-id":
            connection.execute(f"UPDATE {variants} SET capture_event_id=?", ["f" * 64])
        elif kind == "audit":
            table = native.common.name(connection, "medallion_audit", "job_events")
            connection.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
        else:
            connection.execute(f"UPDATE {variants} SET recorded_at=recorded_at+INTERVAL '1 second'")
    with pytest.raises(ValueError):
        read(bronze, result)


def test_changed_review_pin_cannot_heal_source_scope(tmp_path):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_spot_features(source, source_label="fixture")
        with pytest.raises(ValueError, match="REVIEWED_SPOT_FEATURE_SOURCE_CHANGED"):
            native.preserve_spot_features(
                source,
                b,
                source_label="fixture",
                expected_snapshot_id="0" * 64,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            native.preserve_spot_features(
                source,
                b,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="other",
                code_revision="b" * 40,
            )


def test_extra_scoped_job_not_hidden(tmp_path):
    _legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(bronze)) as connection:
        ledger = AuditLedger(connection)
        job = ledger.plan_job(
            command_name=native.COMMAND,
            actor_id="synthetic",
            code_revision=REVISION,
            scope_ref="sha256:" + native.scope_id("fixture"),
            config_hash="b" * 64,
        )
        ledger.transition(job, JobState.FAILED, "EXECUTION_ERROR")
    with pytest.raises(ValueError):
        read(bronze, result)


def test_retained_native_and_current_legacy_are_distinct(tmp_path):
    legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(legacy)) as connection:
        table = native.common.name(connection, "main", codec.TABLE)
        connection.execute(f"UPDATE {table} SET close=999.0")
    assert len(read(bronze, result)) == 3
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze), read_only=True) as connection,
        pytest.raises(ValueError, match="CURRENT"),
    ):
        native.revalidate_spot_features_source(source, connection, **args(result))


def test_injected_variant_sql_failure_rolls_back_native_rows(tmp_path):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_spot_features(source, source_label="fixture")

        class Fail:
            def execute(self, sql, parameters=None):
                if sql.lstrip().startswith("INSERT INTO") and '"event_variants"' in sql:
                    raise RuntimeError("INJECTED_SPOT_FEATURE_VARIANT_SQL_FAILURE")
                return b.execute(sql) if parameters is None else b.execute(sql, parameters)

        with pytest.raises(RuntimeError, match="VARIANT_SQL_FAILURE"):
            native.preserve_spot_features(
                source,
                Fail(),
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for name in ("event_variants", "input_artifacts", "ingest_batches"):
            table = native.common.name(b, "bronze", name)
            assert b.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            native.preserve_spot_features(
                source,
                b,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )


def test_final_audit_failure_blocks_original_recording(tmp_path, monkeypatch):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    original = AuditLedger.transition

    def fail(self, job, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_SPOT_FEATURE_FINAL_AUDIT")
        return original(self, job, state, reason_code)

    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_spot_features(source, source_label="fixture")
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
            native.preserve_spot_features(
                source,
                b,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        monkeypatch.setattr(AuditLedger, "transition", original)
        table = native.common.name(b, "bronze", "event_variants")
        row = b.execute(f"SELECT capture_event_id,envelope_hash FROM {table}").fetchone()
        assert row is not None
    with (
        duckdb.connect(str(bronze), read_only=True) as connection,
        pytest.raises(ValueError, match="AUDIT_NOT_VERIFIED"),
    ):
        native.read_spot_features_bronze(
            connection,
            source_label="fixture",
            snapshot_id=snapshot.snapshot_id,
            capture_event_id=row[0],
            envelope_hash=row[1],
            expected_recording_fingerprint="a" * 64,
        )


def test_timezone_readonly_and_same_live_alias(tmp_path):
    legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(legacy), read_only=True) as source:
        first = native.capture_spot_features(source, source_label="fixture")
        source.execute("SET TimeZone='Asia/Kolkata'")
        assert native.capture_spot_features(source, source_label="fixture") == first
    with duckdb.connect(str(bronze)) as connection:
        with pytest.raises(ValueError, match="READONLY"):
            native.read_spot_features_bronze(connection, **args(result))
        alias = connection.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                native.preserve_spot_features(
                    alias,
                    connection,
                    source_label="fixture",
                    expected_snapshot_id=result["snapshot_id"],
                    imported_at=IMPORT_AT,
                    actor_id="synthetic",
                    code_revision=REVISION,
                )
            assert connection.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()
