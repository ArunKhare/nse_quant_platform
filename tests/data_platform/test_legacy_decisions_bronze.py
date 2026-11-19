"""Actual decision/system-event writers, native Bronze chain, and adversarial boundaries."""

from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import legacy_decisions as codec
from nse_quant.data_platform import legacy_decisions_bronze as native
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.persistence.repositories import DecisionRepository

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
IMPORT_AT = datetime(2026, 1, 2, tzinfo=UTC)
REVISION = "a" * 40


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        repository = DecisionRepository(legacy.conn)
        repository.save_decision(
            "RUN",
            "strategy_decision",
            None,
            {"selected": False, "reason": "no eligible proposal"},
        )
        repository.save_system_event(
            "RUN",
            "system_event",
            {"event": "startup", "level": "info"},
        )
        table = native.common.name(legacy.conn, "main", codec.TABLE)
        legacy.conn.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,CAST(? AS JSON))",
            [
                "C",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                '{"duplicate":1,"duplicate":2}',
            ],
        )
    finally:
        legacy.close()


def record(tmp_path):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_decisions(source, source_label="fixture")
        result = native.preserve_decisions(
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
        return native.read_decisions_bronze(connection, **args(result))


def test_actual_writers_and_native_chain_retain_every_field(tmp_path):
    legacy, bronze, result = record(tmp_path)
    rows = read(bronze, result)
    assert len(rows) == result["row_count"] == 3
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze), read_only=True) as connection,
    ):
        assert native.revalidate_decisions_source(source, connection, **args(result)) == rows
        table = native.common.name(source, "main", codec.TABLE)
        originals = source.execute(
            f"SELECT decision_id,ts,run_id,decision_type,proposal_id,strategy,"
            f"underlying,expiry,CAST(payload AS VARCHAR) FROM {table}"
        ).fetchall()
        by_id = {row[0]: row for row in originals}
        for ordinal, raw in enumerate(rows):
            document = codec.parse(raw, codec.MAX_RECORD)
            fields = document["stored_fields"]
            assert document["source_ordinal"] == ordinal
            assert fields["decision_id"] in by_id
            assert not document["original_decision_execution_replayed"]
            assert not document["native_decision_replayed"]
            assert not document["decision_eligibility_asserted"]
        types = {row[3] for row in originals}
        assert types == {None, "strategy_decision", "system_event"}
        assert by_id["C"][1] is None
        assert by_id["C"][7] is None
        assert by_id["C"][8] == '{"duplicate":1,"duplicate":2}'
        assert all(row[7] is None for row in originals)


def test_retained_decision_is_not_native_admission(tmp_path):
    _legacy, bronze, result = record(tmp_path)
    for raw in read(bronze, result):
        document = codec.parse(raw, codec.MAX_RECORD)
        assert document["classification"] == "RETAINED_LEGACY_DECISION_NOT_NATIVE_ADMISSION"
        assert document["decision_type_semantics"] == (
            "RETAINED_LEGACY_LABEL_NOT_NATIVE_DECISION_SEMANTICS"
        )
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
        snapshot = native.capture_decisions(source, source_label="fixture")
        with pytest.raises(ValueError, match="REVIEWED_DECISION_SOURCE_CHANGED"):
            native.preserve_decisions(
                source,
                b,
                source_label="fixture",
                expected_snapshot_id="0" * 64,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            native.preserve_decisions(
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
        connection.execute(f"UPDATE {table} SET decision_type='changed'")
    assert len(read(bronze, result)) == 3
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze), read_only=True) as connection,
        pytest.raises(ValueError, match="CURRENT"),
    ):
        native.revalidate_decisions_source(source, connection, **args(result))


def test_injected_variant_sql_failure_rolls_back_native_rows(tmp_path):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_decisions(source, source_label="fixture")

        class Fail:
            def execute(self, sql, parameters=None):
                if sql.lstrip().startswith("INSERT INTO") and '"event_variants"' in sql:
                    raise RuntimeError("INJECTED_DECISION_VARIANT_SQL_FAILURE")
                return b.execute(sql) if parameters is None else b.execute(sql, parameters)

        with pytest.raises(RuntimeError, match="VARIANT_SQL_FAILURE"):
            native.preserve_decisions(
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
            native.preserve_decisions(
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
            raise RuntimeError("SYNTHETIC_DECISION_FINAL_AUDIT")
        return original(self, job, state, reason_code)

    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_decisions(source, source_label="fixture")
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
            native.preserve_decisions(
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
        native.read_decisions_bronze(
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
        first = native.capture_decisions(source, source_label="fixture")
        source.execute("SET TimeZone='Asia/Kolkata'")
        assert native.capture_decisions(source, source_label="fixture") == first
    with duckdb.connect(str(bronze)) as connection:
        with pytest.raises(ValueError, match="READONLY"):
            native.read_decisions_bronze(connection, **args(result))
        alias = connection.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                native.preserve_decisions(
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
