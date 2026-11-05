"""Actual initialized legacy schema + explicit synthetic SQL -> real native Bronze.

The legacy evidence writer method was not retrieved. These fixtures do NOT claim
its serialization/upsert semantics or original plugin/decision execution.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_evidence_snapshot_bronze as native
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, tzinfo=UTC)
IMPORT_AT = datetime(2026, 1, 2, tzinfo=UTC)
OPAQUE = ' { "eligible":true, "eligible":false, "available":true } '


def seed(path: Path) -> None:
    owner = DuckDBStore(path=path)
    try:
        table = native.common.name(owner.conn, "main", native.codec.TABLE)
        for i, (symbol, payload) in enumerate([("S", OPAQUE), (None, None), ("S", "null")]):
            owner.conn.execute(
                f"INSERT INTO {table} VALUES (?,?,?,?,CAST(? AS JSON))",
                ["R", AT + timedelta(seconds=i), symbol, f"P-{i}", payload],
            )
    finally:
        owner.close()


def record(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze)) as target,
    ):
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_evidence_snapshots(source, source_label="fixture")
        result = native.preserve_evidence_snapshots(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=IMPORT_AT,
            actor_id="synthetic",
            code_revision="a" * 40,
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
    with duckdb.connect(str(path), read_only=True) as c:
        return native.read_evidence_snapshot_bronze(c, **args(result))


def test_actual_retained_sql_and_native_producer_reader(tmp_path):
    legacy, bronze, result = record(tmp_path)
    rows = read(bronze, result)
    assert len(rows) == result["row_count"] == 3
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze), read_only=True) as b,
    ):
        assert rows == native.revalidate_evidence_snapshot_source(source, b, **args(result))
        table = native.common.name(source, "main", native.codec.TABLE)
        originals = source.execute(
            f"SELECT run_id,ts,symbol,plugin_name,CAST(payload_json AS VARCHAR) FROM {table}"
        ).fetchall()
    by_key = {
        (r[0], native.codec.encode_cell(r[1], "TIMESTAMP WITH TIME ZONE"), r[3]): r
        for r in originals
    }
    payloads = []
    for ordinal, raw in enumerate(rows):
        doc = native.codec.parse(raw, native.codec.MAX_RECORD)
        fields = doc["stored_fields"]
        original = by_key[(fields["run_id"], fields["ts"], fields["plugin_name"])]
        assert fields == {
            n: native.codec.encode_cell(v, kind)
            for v, (n, kind) in zip(original, native.codec.SCHEMA, strict=True)
        }
        payloads.append(fields["payload_json"])
        assert doc["source_ordinal"] == ordinal
        assert doc["stored_ts_instant"] == fields["ts"]
        assert not doc["payload_interpreted"]
        assert not doc["native_decision_replayed"]
        assert not doc["decision_eligibility_asserted"]
        assert doc["original_availability_at"] is None
    assert payloads[1:] == [None, "null"]  # First payload was compared to retained SQL above.


def test_current_legacy_equality_is_not_original_recording_replay(tmp_path):
    legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(legacy)) as c:
        table = native.common.name(c, "main", native.codec.TABLE)
        c.execute(f"UPDATE {table} SET symbol='changed'")
    assert len(read(bronze, result)) == 3
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze), read_only=True) as b,
        pytest.raises(ValueError, match="CURRENT"),
    ):
        native.revalidate_evidence_snapshot_source(source, b, **args(result))


@pytest.mark.parametrize(
    "case",
    ["view", "naive", "text-payload", "null-key", "duplicate", "empty", "overflow"],
    ids=["view", "naive", "text-not-json", "null-key", "duplicate", "empty", "overflow"],
)
def test_exact_schema_keys_and_whole_table_count(tmp_path, case):
    path = tmp_path / "legacy.duckdb"
    with duckdb.connect(str(path)) as c:
        table = native.common.name(c, "main", native.codec.TABLE)
        if case == "view":
            c.execute(f"CREATE VIEW {table} AS SELECT 1 AS wrong")
        else:
            columns = []
            for n, kind in native.codec.SCHEMA:
                if n == "ts" and case == "naive":
                    kind = "TIMESTAMP"
                if n == "payload_json" and case == "text-payload":
                    kind = "VARCHAR"
                columns.append(f'"{n}" {kind}')
            c.execute(f"CREATE TABLE {table} ({','.join(columns)})")
            if case != "empty":
                c.execute(
                    f"INSERT INTO {table} VALUES (?,?,?,?,?)",
                    [None if case == "null-key" else "R", AT, "S", "P", "null"],
                )
            if case == "duplicate":
                c.execute(
                    f"INSERT INTO {table} SELECT run_id,ts,'other',plugin_name,payload_json "
                    f"FROM {table}"
                )
            elif case == "overflow":
                c.execute(f"INSERT INTO {table} SELECT t.* FROM {table} t CROSS JOIN range(1000)")
    with duckdb.connect(str(path), read_only=True) as c, pytest.raises(ValueError):
        native.capture_evidence_snapshots(c, source_label="fixture")


@pytest.mark.parametrize(
    "case",
    ["payload", "artifact", "audit", "scope", "clock"],
    ids=["payload", "artifact", "audit", "job-scope", "clock"],
)
def test_original_recording_integrity(tmp_path, case):
    _legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(bronze)) as c:
        if case == "payload":
            table = native.common.name(c, "bronze", "event_variants")
            c.execute(f"UPDATE {table} SET payload='bad'::BLOB")
        elif case == "artifact":
            table = native.common.name(c, "bronze", "input_artifacts")
            c.execute(f"UPDATE {table} SET artifact_bytes='bad'::BLOB")
        elif case == "audit":
            table = native.common.name(c, "medallion_audit", "job_events")
            c.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
        elif case == "scope":
            table = native.common.name(c, "medallion_audit", "jobs")
            c.execute(f"UPDATE {table} SET scope_ref='bad'")
        else:
            table = native.common.name(c, "bronze", "event_variants")
            c.execute(f"UPDATE {table} SET recorded_at=recorded_at+INTERVAL '1 second'")
    with pytest.raises(ValueError):
        read(bronze, result)


def test_wrong_review_cannot_heal_original_scope(tmp_path):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze)) as target,
    ):
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_evidence_snapshots(source, source_label="fixture")
        options = dict(
            source_label="fixture",
            imported_at=IMPORT_AT,
            actor_id="synthetic",
            code_revision="a" * 40,
        )
        with pytest.raises(ValueError, match="REVIEWED"):
            native.preserve_evidence_snapshots(
                source, target, expected_snapshot_id="0" * 64, **options
            )
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            native.preserve_evidence_snapshots(
                source, target, expected_snapshot_id=snapshot.snapshot_id, **options
            )


def test_final_audit_failure_blocks_recording_and_adoption(tmp_path, monkeypatch):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    original = AuditLedger.transition

    def fail(self, job, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT")
        return original(self, job, state, reason_code)

    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze)) as target,
    ):
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_evidence_snapshots(source, source_label="fixture")
        options = dict(
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=IMPORT_AT,
            actor_id="synthetic",
            code_revision="a" * 40,
        )
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
            native.preserve_evidence_snapshots(source, target, **options)
        monkeypatch.setattr(AuditLedger, "transition", original)
        table = native.common.name(target, "bronze", "event_variants")
        row = target.execute(f"SELECT capture_event_id,envelope_hash FROM {table}").fetchone()
        assert row is not None
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            native.preserve_evidence_snapshots(source, target, **options)
    with duckdb.connect(str(bronze), read_only=True) as c, pytest.raises(ValueError, match="AUDIT"):
        native.read_evidence_snapshot_bronze(
            c,
            source_label="fixture",
            snapshot_id=snapshot.snapshot_id,
            capture_event_id=row[0],
            envelope_hash=row[1],
            expected_recording_fingerprint="b" * 64,
        )


def test_partial_native_sql_failure_rolls_back_all_domain_rows(tmp_path):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze)) as owner,
    ):
        AuditLedger(owner).initialize()
        BronzeEventStore(owner).initialize()
        snapshot = native.capture_evidence_snapshots(source, source_label="fixture")

        class Failure:
            def execute(self, sql: str, parameters: Any = None) -> Any:
                if sql.lstrip().startswith("INSERT INTO") and '"event_variants"' in sql:
                    raise RuntimeError("SYNTHETIC_VARIANT_SQL_FAILURE")
                return owner.execute(sql) if parameters is None else owner.execute(sql, parameters)

        with pytest.raises(RuntimeError, match="VARIANT_SQL_FAILURE"):
            native.preserve_evidence_snapshots(
                source,
                Failure(),
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision="a" * 40,
            )
        for n in ("event_variants", "input_artifacts", "ingest_batches"):
            table = native.common.name(owner, "bronze", n)
            assert owner.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            native.preserve_evidence_snapshots(
                source,
                owner,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision="a" * 40,
            )


def test_timezone_capture_bytes_invariant_and_same_file_alias(tmp_path):
    path = tmp_path / "legacy.duckdb"
    seed(path)
    with duckdb.connect(str(path), read_only=True) as source:
        source.execute("SET TimeZone='UTC'")
        first = native.capture_evidence_snapshots(source, source_label="fixture")
        source.execute("SET TimeZone='Asia/Kolkata'")
        assert native.capture_evidence_snapshots(source, source_label="fixture") == first
        alias = source.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                native.preserve_evidence_snapshots(
                    source,
                    alias,
                    source_label="fixture",
                    expected_snapshot_id=first.snapshot_id,
                    imported_at=IMPORT_AT,
                    actor_id="synthetic",
                    code_revision="a" * 40,
                )
            assert source.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()


@pytest.mark.parametrize("size", [65536, 65537], ids=["json-text-limit", "json-text-overflow"])
def test_sql_json_text_transfer_limit(tmp_path, size):
    path = tmp_path / "legacy.duckdb"
    seed(path)
    with duckdb.connect(str(path)) as c:
        table = native.common.name(c, "main", native.codec.TABLE)
        c.execute(
            f"UPDATE {table} SET payload_json=CAST(? AS JSON)", ['"' + "x" * (size - 2) + '"']
        )
    with duckdb.connect(str(path), read_only=True) as source:
        if size > native.codec.MAX_CELL:
            with pytest.raises(ValueError, match="TRANSFER_BOUND"):
                native.capture_evidence_snapshots(source, source_label="fixture")
        else:
            assert native.capture_evidence_snapshots(source, source_label="fixture").row_count == 3


def test_first_write_precedes_actual_capture(tmp_path, monkeypatch):
    legacy, bronze, result = record(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("source capture must not run")

    monkeypatch.setattr(native, "capture_evidence_snapshots", forbidden)
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze)) as target,
        pytest.raises(ValueError, match="FIRST_WRITE"),
    ):
        native.preserve_evidence_snapshots(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=result["snapshot_id"],
            imported_at=IMPORT_AT,
            actor_id="synthetic",
            code_revision="a" * 40,
        )


@pytest.mark.parametrize(
    "state",
    ["PLANNED", "RUNNING", "FAILED", "CANCELLED"],
    ids=["planned", "running", "failed", "cancelled"],
)
def test_extra_scoped_jobs_cannot_hide_original_obligation(tmp_path, state):
    _legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(bronze)) as c:
        ledger = AuditLedger(c)
        job = ledger.plan_job(
            command_name=native.COMMAND,
            actor_id="synthetic",
            code_revision="a" * 40,
            config_hash="b" * 64,
            scope_ref="sha256:" + native.scope_id("fixture"),
        )
        if state != "PLANNED":
            ledger.transition(job, JobState(state))
    with pytest.raises(ValueError):
        read(bronze, result)


def test_bronze_session_timezone_does_not_change_original_recording_pin(tmp_path):
    _legacy, bronze, result = record(tmp_path)
    first = read(bronze, result)
    with duckdb.connect(str(bronze), read_only=True) as c:
        c.execute("SET TimeZone='Asia/Kolkata'")
        assert native.read_evidence_snapshot_bronze(c, **args(result)) == first


def test_projection_limit_rejects_before_native_append(tmp_path):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with duckdb.connect(str(legacy)) as c:
        table = native.common.name(c, "main", native.codec.TABLE)
        c.execute(f"DELETE FROM {table}")
        c.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,CAST(? AS JSON))",
            ["r" * 65536, AT, "\x01" * 65536, "\x01" * 65536, "null"],
        )
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze)) as target,
    ):
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_evidence_snapshots(source, source_label="fixture")
        with pytest.raises(ValueError, match="RECORD_BYTE_BOUND"):
            native.preserve_evidence_snapshots(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision="a" * 40,
            )
        for n in ("event_variants", "input_artifacts", "ingest_batches"):
            table = native.common.name(target, "bronze", n)
            assert target.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
