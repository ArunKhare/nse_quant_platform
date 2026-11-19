"""Actual legacy writer -> actual native Bronze -> persisted naive-wall evidence Silver."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import duckdb
import pytest
from test_legacy_decision_evidence_bronze import OPAQUE, REVISION, _record

from nse_quant.data_platform import legacy_decision_evidence_silver as store
from nse_quant.data_platform.audit import AuditLedger, JobState


@pytest.fixture
def target(tmp_path: Path) -> tuple[Any, ...]:
    legacy, bronze, receipt = _record(tmp_path)
    pins = store.DecisionEvidenceBronzePins(
        receipt["source_label"],
        receipt["snapshot_id"],
        receipt["capture_event_id"],
        receipt["envelope_hash"],
        receipt["recording_fingerprint"],
    )
    silver = tmp_path / "silver.duckdb"  # Actual catalog/schema collision is preserved.
    with duckdb.connect(str(silver)) as c:
        store.initialize_decision_evidence_silver(c)
    with duckdb.connect(str(bronze), read_only=True) as c:
        context = store.observe_decision_evidence_bronze(c, pins=pins)
    return legacy, bronze, silver, pins, store.codec.sha(context)


def build(target: tuple[Any, ...], **changes: Any) -> dict[str, Any]:
    args = dict(
        pins=target[3],
        expected_context_sha256=target[4],
        actor_id="synthetic",
        code_revision=REVISION,
    )
    args.update(changes)
    with (
        duckdb.connect(str(target[1]), read_only=True) as bronze,
        duckdb.connect(str(target[2])) as silver,
    ):
        return store.persist_decision_evidence_silver(bronze, silver, **args)


def read(target: tuple[Any, ...], result: dict[str, Any], mode: str = "retained"):
    args = dict(
        revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(target[2]), read_only=True) as silver:
        if mode == "retained":
            return store.read_decision_evidence_silver(silver, **args)
        with duckdb.connect(str(target[1]), read_only=True) as bronze:
            if mode == "bronze":
                return store.revalidate_decision_evidence_silver(bronze, silver, **args)
            with duckdb.connect(str(target[0]), read_only=True) as legacy:
                return store.revalidate_decision_evidence_silver_source(
                    legacy, bronze, silver, **args
                )


def test_actual_writer_native_chain_all_seven_fields_and_three_read_modes(target):
    result = build(target)
    rows = read(target, result)
    assert len(rows) == result["row_count"] == 3
    assert rows == read(target, result, "bronze") == read(target, result, "legacy")
    with duckdb.connect(str(target[0]), read_only=True) as legacy:
        table = store.common.name(legacy, "main", store.codec.TABLE)
        columns = ",".join('"' + n + '"' for n, _kind in store.codec.SCHEMA)
        originals = legacy.execute(f"SELECT {columns} FROM {table}").fetchall()
    by_id = {row[0]: row for row in originals}
    for ordinal, raw in enumerate(rows):
        doc = store.codec.parse(raw, store.MAX_RECORD_BYTES)
        fields = doc["stored_fields"]
        original = by_id[fields["evidence_id"]]
        assert fields == {
            n: store.codec.encode_cell(v, kind)
            for v, (n, kind) in zip(original, store.codec.SCHEMA, strict=True)
        }
        assert doc["source_ordinal"] == ordinal
        assert doc["stored_ts_instant"] is None
        assert doc["source_timezone"] is None
        assert doc["original_availability_at"] is None
        assert doc["payload_interpreted"] is False
        assert doc["native_decision_replayed"] is False
        assert not doc["decision_eligibility_asserted"]
    opaque = next(
        store.codec.parse(r, store.MAX_RECORD_BYTES)
        for r in rows
        if store.codec.parse(r, store.MAX_RECORD_BYTES)["stored_fields"]["evidence_id"] == "opaque"
    )
    assert opaque["stored_fields"]["payload_json"] == OPAQUE
    assert opaque["stored_fields"]["available"] is True
    with duckdb.connect(str(target[2]), read_only=True) as silver:
        table = store.common.name(silver, "silver", store.DOMAIN[2])
        stored = silver.execute(
            f"SELECT ts,available,payload_json FROM {table} WHERE evidence_id='opaque'"
        ).fetchone()
        assert stored is not None and stored[0].tzinfo is None
        assert stored[1:] == (True, OPAQUE)
        kinds = silver.execute(
            "SELECT data_type FROM information_schema.columns WHERE table_catalog="
            "current_database() AND table_schema='silver' AND table_name=? AND column_name='ts'",
            [store.DOMAIN[2]],
        ).fetchall()
        assert kinds == [("TIMESTAMP",)]


@pytest.mark.parametrize(
    "column,value",
    [
        ("evidence_id", "'changed'"),
        ("run_id", "'changed'"),
        ("ts", "ts+INTERVAL '1 second'"),
        ("symbol", "'changed'"),
        ("plugin", "'changed'"),
        ("available", "NOT available"),
        ("payload_json", "'changed'"),
        ("record_bytes", "'bad'::BLOB"),
        ("record_id", "'bad'"),
        ("source_observation_id", "'bad'"),
    ],
    ids=[
        "id",
        "run",
        "wall-ts",
        "symbol",
        "plugin",
        "available",
        "opaque-text",
        "bytes",
        "record-hash",
        "source-event",
    ],
)
def test_full_materialized_scalar_and_bytes_recomputed(target, column, value):
    result = build(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        c.execute(f"UPDATE {table} SET {column}={value} WHERE ordinal=0")
    with pytest.raises(ValueError):
        read(target, result)


@pytest.mark.parametrize(
    "case",
    ["missing", "attempt", "audit", "contract", "definition", "scope"],
    ids=["row", "attempt", "audit", "contract", "definition", "job-scope"],
)
def test_original_obligations_no_good_subset(target, case):
    result = build(target)
    with duckdb.connect(str(target[2])) as c:
        if case == "missing":
            table = store.common.name(c, "silver", store.DOMAIN[2])
            c.execute(f"DELETE FROM {table} WHERE ordinal=0")
        elif case == "attempt":
            c.execute(f"DELETE FROM {store.common.name(c, 'silver', store.DOMAIN[3])}")
        elif case == "audit":
            table = store.common.name(c, "medallion_audit", "job_events")
            c.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
        elif case == "contract":
            table = store.common.name(c, "medallion_audit", "dataset_contracts")
            c.execute(f"UPDATE {table} SET fingerprint='bad'")
        elif case == "definition":
            table = store.common.name(c, "silver", store.DOMAIN[0])
            c.execute(f"UPDATE {table} SET definition='bad'::BLOB")
        else:
            table = store.common.name(c, "medallion_audit", "jobs")
            c.execute(f"UPDATE {table} SET scope_ref='bad'")
    with pytest.raises(ValueError):
        read(target, result)


@pytest.mark.parametrize(
    "state",
    ["PLANNED", "RUNNING", "FAILED", "CANCELLED"],
    ids=["planned", "running", "failed", "cancelled"],
)
def test_extra_original_scoped_job_cannot_hide(target, state):
    result = build(target)
    with duckdb.connect(str(target[2])) as c:
        ledger = AuditLedger(c)
        job = ledger.plan_job(
            command_name=store.COMMAND,
            actor_id="synthetic",
            code_revision=REVISION,
            scope_ref="sha256:" + target[3].scope_id,
            config_hash="b" * 64,
        )
        if state != "PLANNED":
            ledger.transition(job, JobState(state))
    with pytest.raises(ValueError):
        read(target, result)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(target)


def test_recording_or_envelope_pin_change_cannot_heal_scope(target):
    bad = replace(target[3], recording_fingerprint="0" * 64)
    assert bad.scope_id == target[3].scope_id
    assert replace(target[3], envelope_hash="f" * 64).scope_id == target[3].scope_id
    with pytest.raises(ValueError):
        build(target, pins=bad)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(target)


def test_bad_reviewed_context_cannot_heal(target):
    with pytest.raises(ValueError, match="REVIEWED"):
        build(target, expected_context_sha256="0" * 64)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(target)


def test_first_write_before_native_reader(target, monkeypatch):
    build(target)

    def forbidden(*args, **kwargs):
        raise AssertionError("source must not be observed")

    monkeypatch.setattr(store.source, "read_decision_evidence_bronze", forbidden)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(target)


def test_second_actual_public_reader_failure_no_partial_domain(target, monkeypatch):
    actual = store.source.read_decision_evidence_bronze
    calls = 0

    def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_NATIVE_READ")
        return actual(*args, **kwargs)

    monkeypatch.setattr(store.source, "read_decision_evidence_bronze", fail)
    with pytest.raises(RuntimeError, match="SECOND_NATIVE_READ"):
        build(target)
    with duckdb.connect(str(target[2]), read_only=True) as c:
        for n in store.DOMAIN[1:]:
            table = store.common.name(c, "silver", n)
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(target)


def test_actual_sql_failure_rolls_back_set_rows_and_attempt(target):
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[3])
        c.execute(f"ALTER TABLE {table} ADD COLUMN synthetic_failure INTEGER DEFAULT 0")
    with pytest.raises(duckdb.Error):
        build(target)
    with duckdb.connect(str(target[2]), read_only=True) as c:
        for n in store.DOMAIN[1:]:
            table = store.common.name(c, "silver", n)
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(target)


def test_final_audit_failure_after_domain_is_unreadable_and_not_adoptable(target, monkeypatch):
    actual = AuditLedger.transition

    def fail(self, job, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT")
        return actual(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail)
    with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
        build(target)
    monkeypatch.setattr(AuditLedger, "transition", actual)
    with duckdb.connect(str(target[2]), read_only=True) as c:
        table = store.common.name(c, "silver", store.DOMAIN[1])
        row = c.execute(f"SELECT revision_id FROM {table}").fetchone()
        assert row is not None
        with pytest.raises(ValueError, match="AUDIT"):
            store.read_decision_evidence_silver(
                c, revision_id=row[0], expected_recording_fingerprint="a" * 64
            )
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(target)


def test_same_capture_orphan_and_extra_revision_not_adopted(target):
    result = build(target)
    with duckdb.connect(str(target[2])) as c:
        rows = store.common.name(c, "silver", store.DOMAIN[2])
        columns = ",".join('"' + n + '"' for n, _kind in store.codec.SCHEMA)
        c.execute(
            f"INSERT INTO {rows} SELECT ?,ordinal,record_id,{columns},record_bytes,"
            f"source_observation_id,recorded_at FROM {rows} WHERE ordinal=0",
            ["f" * 64],
        )
    with pytest.raises(ValueError):
        read(target, result)
    with duckdb.connect(str(target[2])) as c:
        for schema, n in (
            ("silver", store.DOMAIN[1]),
            ("silver", store.DOMAIN[3]),
            ("medallion_audit", "job_events"),
            ("medallion_audit", "jobs"),
        ):
            c.execute(f"DELETE FROM {store.common.name(c, schema, n)}")
    with pytest.raises(ValueError, match="ORPHAN"):
        build(target)


@pytest.mark.parametrize(
    "column,size",
    [
        ("record_bytes", 4194305),
        ("record_bytes", 524289),
        ("payload_json", 65537),
    ],
    ids=["records-total", "record-cell", "opaque-text-cell"],
)
def test_independent_sql_transfer_bounds(target, column, size):
    result = build(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        expression = "encode(repeat('x',?))" if column == "record_bytes" else "repeat('x',?)"
        c.execute(f"UPDATE {table} SET {column}={expression} WHERE ordinal=0", [size])
    with pytest.raises(ValueError, match="TRANSFER_BOUND"):
        read(target, result)


def test_materialized_text_aggregate_preflight_is_independent(target):
    result = build(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        columns = ",".join(
            '"' + n + '"' + "=repeat('x',65536)"
            for n, kind in store.codec.SCHEMA
            if kind == "VARCHAR"
        )
        c.execute(f"UPDATE {table} SET {columns}")
        # Four same-source rows exceed 1 MiB while each text cell remains exactly at its bound.
        names = ",".join('"' + n + '"' for n, _kind in store.codec.SCHEMA)
        c.execute(
            f"INSERT INTO {table} SELECT revision_id,100,record_id,{names},record_bytes,"
            f"source_observation_id,recorded_at FROM {table} WHERE ordinal=0"
        )
    with pytest.raises(ValueError, match="TRANSFER_BOUND"):
        read(target, result)


def test_retained_bronze_and_current_legacy_are_distinct(target):
    result = build(target)
    with duckdb.connect(str(target[0])) as legacy:
        table = store.common.name(legacy, "main", store.codec.TABLE)
        legacy.execute(f"UPDATE {table} SET available=NOT available")
    assert len(read(target, result)) == len(read(target, result, "bronze")) == 3
    with pytest.raises(ValueError, match="CURRENT_LEGACY"):
        read(target, result, "legacy")
    with duckdb.connect(str(target[1])) as bronze:
        table = store.common.name(bronze, "medallion_audit", "job_events")
        bronze.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    assert len(read(target, result)) == 3
    with pytest.raises(ValueError):
        read(target, result, "bronze")


def test_timezone_does_not_convert_naive_wall_fields_or_change_recording_pin(target):
    result = build(target)
    args = dict(
        revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(target[2]), read_only=True) as c:
        c.execute("SET TimeZone='UTC'")
        first = store.read_decision_evidence_silver(c, **args)
        table = store.common.name(c, "silver", store.DOMAIN[2])
        walls = c.execute(f"SELECT ts FROM {table} ORDER BY ordinal").fetchall()
        c.execute("SET TimeZone='Asia/Kolkata'")
        assert store.read_decision_evidence_silver(c, **args) == first
        assert c.execute(f"SELECT ts FROM {table} ORDER BY ordinal").fetchall() == walls
        assert all(w[0].tzinfo is None for w in walls)


def test_recording_clock_drift_requires_original_pin(target):
    result = build(target)
    with duckdb.connect(str(target[2])) as c:
        for n in store.DOMAIN[1:3]:
            table = store.common.name(c, "silver", n)
            c.execute(f"UPDATE {table} SET recorded_at=recorded_at+INTERVAL '1 second'")
    with pytest.raises(ValueError, match="FINGERPRINT"):
        read(target, result)


def test_same_live_file_alias_preserves_parent(target):
    with duckdb.connect(str(target[1]), read_only=True) as c:
        alias = c.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                store.persist_decision_evidence_silver(
                    c,
                    alias,
                    pins=target[3],
                    expected_context_sha256=target[4],
                    actor_id="synthetic",
                    code_revision=REVISION,
                )
            assert c.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()


def test_public_reader_readonly_and_no_reinitialization(target):
    result = build(target)
    with duckdb.connect(str(target[2])) as c:
        with pytest.raises(ValueError):
            store.read_decision_evidence_silver(
                c,
                revision_id=result["revision_id"],
                expected_recording_fingerprint=result["recording_fingerprint"],
            )
        with pytest.raises(ValueError, match="EMPTY"):
            store.initialize_decision_evidence_silver(c)


@pytest.mark.parametrize(
    "field,kind",
    [("ts", "TIMESTAMPTZ"), ("available", "INTEGER")],
    ids=["aware-wall-type", "integer-availability"],
)
def test_materialized_types_cannot_silently_coerce_wall_or_boolean(target, field, kind):
    result = build(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        c.execute(f'ALTER TABLE {table} ALTER COLUMN "{field}" TYPE {kind}')
    with pytest.raises(ValueError):
        read(target, result)
