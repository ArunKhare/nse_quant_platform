"""Actual retrieved legacy writers and explicit SQL boundaries -> actual native Bronze."""

from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import legacy_gate_results as codec
from nse_quant.data_platform import legacy_gate_results_bronze as native
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
IMPORT_AT = datetime(2026, 1, 2, tzinfo=UTC)
REVISION = "a" * 40


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        legacy.write_feature_gate_result(
            gate_result_id="A",
            ts=AT,
            run_id="R",
            symbol="NIFTY",
            passed=True,
            reasons=["first"],
            checks={"first": True},
        )
        legacy.write_feature_gate_result(
            gate_result_id="A",
            ts=AT,
            run_id="R",
            symbol="NIFTY",
            passed=False,
            reasons=["replacement"],
            checks={"replacement": False},
        )
        legacy.write_feature_availability_result(
            gate_result_id="B",
            ts=AT,
            run_id="R",
            symbol="NIFTY",
            passed=True,
            reasons=["retained"],
            checks={"eligible": True},
        )
        table = native.common.name(legacy.conn, "main", codec.TABLE)
        # Explicit nullable/duplicate-key JSON boundary, not another writer attestation.
        legacy.conn.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,CAST(? AS JSON))",
            ["C", None, None, None, None, None, None, "not-json reason", '{"x":1,"x":2}'],
        )
        # No natural uniqueness axis beyond the actual primary ID is invented.
        legacy.conn.execute(
            f"INSERT INTO {table} SELECT 'D',ts,run_id,proposal_id,strategy,"
            f"gate,passed,reason,details FROM {table} WHERE gate_result_id='A'"
        )
    finally:
        legacy.close()


def record(tmp_path):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_gate_results(source, source_label="fixture")
        result = native.preserve_gate_results(
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
    with duckdb.connect(str(path), read_only=True) as c:
        return native.read_gate_results_bronze(c, **args(result))


def test_actual_writer_upsert_and_native_chain_every_field(tmp_path):
    legacy, bronze, result = record(tmp_path)
    rows = read(bronze, result)
    assert len(rows) == result["row_count"] == 4
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze), read_only=True) as b,
    ):
        assert native.revalidate_gate_results_source(source, b, **args(result)) == rows
        table = native.common.name(source, "main", codec.TABLE)
        originals = source.execute(
            f"SELECT gate_result_id,ts,run_id,proposal_id,strategy,gate,"
            f"passed,reason,CAST(details AS VARCHAR) FROM {table}"
        ).fetchall()
        by_id = {r[0]: r for r in originals}
        for ordinal, raw in enumerate(rows):
            doc = codec.parse(raw, codec.MAX_RECORD)
            fields = doc["stored_fields"]
            assert fields == {
                n: codec.encode_cell(v, kind)
                for v, (n, kind) in zip(by_id[fields["gate_result_id"]], codec.SCHEMA, strict=True)
            }
            assert doc["source_ordinal"] == ordinal
            assert not doc["original_gate_execution_replayed"]
            assert not doc["native_decision_replayed"]
            assert not doc["decision_eligibility_asserted"]
        assert by_id["A"][6] is False  # Actual same-ID INSERT OR REPLACE retained replacement.
        assert by_id["B"][6] is True
        assert by_id["C"][1] is None and by_id["C"][6] is None


@pytest.mark.parametrize(
    "kind",
    ["payload", "artifact", "event-id", "audit", "clock"],
    ids=["payload", "artifact", "id", "audit", "clock"],
)
def test_original_native_recording_tampering(tmp_path, kind):
    _legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(bronze)) as c:
        variants = native.common.name(c, "bronze", "event_variants")
        if kind == "payload":
            c.execute(f"UPDATE {variants} SET payload='bad'::BLOB")
        elif kind == "artifact":
            table = native.common.name(c, "bronze", "input_artifacts")
            c.execute(f"UPDATE {table} SET artifact_bytes='bad'::BLOB")
        elif kind == "event-id":
            c.execute(f"UPDATE {variants} SET capture_event_id=?", ["f" * 64])
        elif kind == "audit":
            table = native.common.name(c, "medallion_audit", "job_events")
            c.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
        else:
            c.execute(f"UPDATE {variants} SET recorded_at=recorded_at+INTERVAL '1 second'")
    with pytest.raises(ValueError):
        read(bronze, result)


def test_changed_review_pin_cannot_heal_source_label_scope(tmp_path):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with duckdb.connect(str(legacy), read_only=True) as s, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_gate_results(s, source_label="fixture")
        with pytest.raises(ValueError, match="REVIEWED_GATE_SOURCE_CHANGED"):
            native.preserve_gate_results(
                s,
                b,
                source_label="fixture",
                expected_snapshot_id="0" * 64,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            native.preserve_gate_results(
                s,
                b,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="other",
                code_revision="b" * 40,
            )


def test_extra_scoped_job_not_hidden(tmp_path):
    _legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(bronze)) as c:
        ledger = AuditLedger(c)
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
    with duckdb.connect(str(legacy)) as c:
        table = native.common.name(c, "main", codec.TABLE)
        c.execute(f"UPDATE {table} SET passed=NOT passed")
    assert len(read(bronze, result)) == 4
    with (
        duckdb.connect(str(legacy), read_only=True) as s,
        duckdb.connect(str(bronze), read_only=True) as b,
        pytest.raises(ValueError, match="CURRENT"),
    ):
        native.revalidate_gate_results_source(s, b, **args(result))


def test_injected_variant_sql_failure_rolls_back_all_native_rows(tmp_path):
    """Actual append failure boundary; proxy raises, not a successful source substitute."""
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with duckdb.connect(str(legacy), read_only=True) as s, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_gate_results(s, source_label="fixture")

        class Fail:
            def execute(self, sql, parameters=None):
                if sql.lstrip().startswith("INSERT INTO") and '"event_variants"' in sql:
                    raise RuntimeError("INJECTED_GATE_VARIANT_SQL_FAILURE")
                return b.execute(sql) if parameters is None else b.execute(sql, parameters)

        with pytest.raises(RuntimeError, match="VARIANT_SQL_FAILURE"):
            native.preserve_gate_results(
                s,
                Fail(),
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for n in ("event_variants", "input_artifacts", "ingest_batches"):
            table = native.common.name(b, "bronze", n)
            assert b.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            native.preserve_gate_results(
                s,
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
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT")
        return original(self, job, state, reason_code)

    with duckdb.connect(str(legacy), read_only=True) as s, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_gate_results(s, source_label="fixture")
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
            native.preserve_gate_results(
                s,
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
        duckdb.connect(str(bronze), read_only=True) as b,
        pytest.raises(ValueError, match="AUDIT_NOT_VERIFIED"),
    ):
        native.read_gate_results_bronze(
            b,
            source_label="fixture",
            snapshot_id=snapshot.snapshot_id,
            capture_event_id=row[0],
            envelope_hash=row[1],
            expected_recording_fingerprint="a" * 64,
        )


def test_timezone_readonly_and_same_live_alias(tmp_path):
    legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(legacy), read_only=True) as s:
        first = native.capture_gate_results(s, source_label="fixture")
        s.execute("SET TimeZone='Asia/Kolkata'")
        assert native.capture_gate_results(s, source_label="fixture") == first
    with duckdb.connect(str(bronze)) as b:
        with pytest.raises(ValueError, match="READONLY"):
            native.read_gate_results_bronze(b, **args(result))
        alias = b.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                native.preserve_gate_results(
                    alias,
                    b,
                    source_label="fixture",
                    expected_snapshot_id=result["snapshot_id"],
                    imported_at=IMPORT_AT,
                    actor_id="synthetic",
                    code_revision=REVISION,
                )
            assert b.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()
