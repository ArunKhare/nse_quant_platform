"""Actual legacy writer -> original native Bronze -> typed persisted evidence Silver."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import duckdb
import pytest
from test_legacy_decision_evidence_bronze import IMPORT_AT, OPAQUE, WALL, _record, _source

from nse_quant.data_platform import legacy_decision_evidence_silver_store as store
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore


def prepared(tmp_path: Path) -> tuple[Any, ...]:
    legacy, bronze, receipt = _record(tmp_path)
    pins = store.DecisionEvidenceBronzePins(
        receipt["source_label"],
        receipt["snapshot_id"],
        receipt["capture_event_id"],
        receipt["envelope_hash"],
        receipt["recording_fingerprint"],
    )
    silver = tmp_path / "silver.duckdb"  # Actual catalog/schema collision, not a renamed fixture.
    with duckdb.connect(str(bronze), read_only=True) as b:
        context = store.observe_decision_evidence_bronze(b, pins=pins)
    with duckdb.connect(str(silver)) as s:
        store.initialize_decision_evidence_silver(s)
    return legacy, bronze, silver, pins, store.codec.sha(context)


def persist(target: tuple[Any, ...], **changes: Any) -> dict[str, Any]:
    args = dict(
        pins=target[3],
        expected_context_sha256=target[4],
        actor_id="synthetic",
        code_revision="a" * 40,
    )
    args.update(changes)
    with duckdb.connect(str(target[1]), read_only=True) as b, duckdb.connect(str(target[2])) as s:
        return store.persist_decision_evidence_silver(b, s, **args)


def read(
    target: tuple[Any, ...], result: dict[str, Any], mode: str = "retained"
) -> tuple[bytes, ...]:
    args = dict(
        revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(target[2]), read_only=True) as s:
        if mode == "retained":
            return store.read_decision_evidence_silver(s, **args)
        with duckdb.connect(str(target[1]), read_only=True) as b:
            if mode == "bronze":
                return store.revalidate_decision_evidence_silver(b, s, **args)
            with duckdb.connect(str(target[0]), read_only=True) as legacy:
                return store.revalidate_decision_evidence_silver_source(legacy, b, s, **args)


def test_actual_chain_every_scalar_wall_boolean_and_opaque_text(tmp_path: Path) -> None:
    target = prepared(tmp_path)
    result = persist(target)
    rows = read(target, result)
    assert rows == read(target, result, "bronze") == read(target, result, "source")
    assert len(rows) == result["row_count"] == 3
    with duckdb.connect(str(target[1]), read_only=True) as bronze:
        assert rows == store.source.read_decision_evidence_bronze(bronze, **target[3].reader_args())
    with duckdb.connect(str(target[2]), read_only=True) as silver:
        table = store.common.name(silver, "silver", store.DOMAIN[2])
        columns = ",".join('"' + n + '"' for n, _ in store.SCHEMA)
        scalars = silver.execute(f"SELECT {columns} FROM {table} ORDER BY ordinal").fetchall()
        for raw, values in zip(rows, scalars, strict=True):
            doc = store.codec.parse(raw, store.MAX_RECORD)
            assert doc["stored_fields"] == {
                n: store.codec.encode_cell(v, kind)
                for v, (n, kind) in zip(values, store.SCHEMA, strict=True)
            }
            assert values[2].tzinfo is None
            assert type(values[5]) is bool
            assert doc["stored_ts_instant"] is None
            assert doc["source_timezone"] is None
            assert doc["payload_interpreted"] is False
            assert doc["native_decision_replayed"] is False
            assert doc["decision_eligibility_asserted"] is False
        assert any(v[5] is True for v in scalars)
        assert any(v[5] is False for v in scalars)
        assert any(v[6] == OPAQUE for v in scalars)
        assert silver.execute(f"SELECT count(*) FROM {table}").fetchone() == (3,)


@pytest.mark.parametrize(
    "column,value",
    [
        ("evidence_id", "evidence_id || '-changed'"),
        ("run_id", "run_id || '-changed'"),
        ("ts", "ts + INTERVAL '1 microsecond'"),
        ("symbol", "'changed'"),
        ("plugin", "'changed'"),
        ("available", "NOT available"),
        ("payload_json", "'changed'"),
        ("record_id", "'bad'"),
        ("record_bytes", "'bad'::BLOB"),
        ("source_observation_id", "'bad'"),
    ],
    ids=[
        "id",
        "run",
        "wall-microsecond",
        "symbol",
        "plugin",
        "boolean",
        "opaque-text",
        "hash",
        "bytes",
        "source-event",
    ],
)
def test_all_materialized_scalar_and_record_corruption(
    tmp_path: Path, column: str, value: str
) -> None:
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        c.execute(f"UPDATE {table} SET {column}={value} WHERE ordinal=0")
    with pytest.raises(ValueError):
        read(target, result)


@pytest.mark.parametrize(
    "case",
    ["row", "attempt", "audit", "contract", "definition", "clock"],
    ids=["missing-row", "link", "audit", "contract", "definition", "clock"],
)
def test_original_recording_and_complete_coverage(tmp_path: Path, case: str) -> None:
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        if case == "row":
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
            table = store.common.name(c, "silver", store.DOMAIN[1])
            c.execute(f"UPDATE {table} SET recorded_at=recorded_at+INTERVAL '1 second'")
    with pytest.raises(ValueError):
        read(target, result)


@pytest.mark.parametrize(
    "field",
    ["snapshot_id", "envelope_hash", "recording_fingerprint", "source_label"],
    ids=["snapshot-review", "envelope-review", "recording-review", "label"],
)
def test_review_changes_do_not_heal_same_capture_event(tmp_path: Path, field: str) -> None:
    target = prepared(tmp_path)
    bad = replace(target[3], **{field: "other" if field == "source_label" else "b" * 64})
    assert bad.scope_id == target[3].scope_id
    with pytest.raises(ValueError):
        persist(target, pins=bad)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        persist(target)


def test_bad_context_pin_leaves_original_failed_scope(tmp_path: Path) -> None:
    target = prepared(tmp_path)
    with pytest.raises(ValueError, match="CONTEXT_CHANGED"):
        persist(target, expected_context_sha256="0" * 64)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        persist(target)


@pytest.mark.parametrize(
    "state",
    ["PLANNED", "RUNNING", "FAILED", "CANCELLED"],
    ids=["planned", "running", "failed", "cancelled"],
)
def test_extra_scoped_jobs_not_hidden(tmp_path: Path, state: str) -> None:
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        ledger = AuditLedger(c)
        job = ledger.plan_job(
            command_name=store.COMMAND,
            actor_id="synthetic",
            code_revision="a" * 40,
            scope_ref="sha256:" + target[3].scope_id,
            config_hash="b" * 64,
        )
        if state != "PLANNED":
            ledger.transition(job, JobState(state))
    with pytest.raises(ValueError):
        read(target, result)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        persist(target)


def test_first_write_precedes_actual_bronze_reader(tmp_path: Path, monkeypatch: Any) -> None:
    target = prepared(tmp_path)
    persist(target)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("source must not be read")

    monkeypatch.setattr(store.source, "read_decision_evidence_bronze", forbidden)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        persist(target)


def test_orphan_same_event_rows_cannot_be_adopted(tmp_path: Path) -> None:
    target = prepared(tmp_path)
    persist(target)
    with duckdb.connect(str(target[2])) as c:
        for schema, table in (
            ("silver", store.DOMAIN[1]),
            ("silver", store.DOMAIN[3]),
            ("medallion_audit", "job_events"),
            ("medallion_audit", "jobs"),
        ):
            c.execute(f"DELETE FROM {store.common.name(c, schema, table)}")
    with pytest.raises(ValueError, match="ORPHAN"):
        persist(target)


def test_same_event_other_revision_cannot_hide_outside_good_subset(tmp_path: Path) -> None:
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        c.execute(
            f"INSERT INTO {table} SELECT ?,ordinal,record_id,evidence_id,run_id,ts,symbol,"
            f"plugin,available,payload_json,record_bytes,source_observation_id,recorded_at "
            f"FROM {table} WHERE ordinal=0",
            ["0" * 64],
        )
    with pytest.raises(ValueError):
        read(target, result)


def test_actual_sql_domain_failure_rolls_back_all_rows(tmp_path: Path) -> None:
    target = prepared(tmp_path)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        c.execute(f"ALTER TABLE {table} ADD COLUMN injected_failure INTEGER DEFAULT 0")
    with pytest.raises(duckdb.Error):
        persist(target)
    with duckdb.connect(str(target[2]), read_only=True) as c:
        for n in store.DOMAIN[1:]:
            table = store.common.name(c, "silver", n)
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        persist(target)


def test_final_audit_failure_not_readable_or_adoptable(tmp_path: Path, monkeypatch: Any) -> None:
    target = prepared(tmp_path)
    original = AuditLedger.transition

    def fail(self: Any, job: str, state: JobState, reason_code: str | None = None) -> None:
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT")
        original(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail)
    with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
        persist(target)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with duckdb.connect(str(target[2]), read_only=True) as c:
        table = store.common.name(c, "silver", store.DOMAIN[1])
        row = c.execute(f"SELECT revision_id FROM {table}").fetchone()
        assert row is not None
        with pytest.raises(ValueError, match="AUDIT_NOT_VERIFIED"):
            store.read_decision_evidence_silver(
                c, revision_id=row[0], expected_recording_fingerprint="a" * 64
            )
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        persist(target)


def test_second_actual_bronze_observation_failure_no_partial_set(
    tmp_path: Path, monkeypatch: Any
) -> None:
    target = prepared(tmp_path)
    original = store.source.read_decision_evidence_bronze
    calls = 0

    def observe(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_BRONZE_READ")
        return original(*args, **kwargs)

    monkeypatch.setattr(store.source, "read_decision_evidence_bronze", observe)
    with pytest.raises(RuntimeError, match="SECOND_BRONZE_READ"):
        persist(target)
    with duckdb.connect(str(target[2]), read_only=True) as c:
        table = store.common.name(c, "silver", store.DOMAIN[1])
        assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        persist(target)


@pytest.mark.parametrize(
    "column,size",
    [("record_bytes", 524289), ("record_bytes", 4194305), ("payload_json", 65537)],
    ids=["record-cell", "record-aggregate", "opaque-text-cell"],
)
def test_sql_resource_preflight(tmp_path: Path, column: str, size: int) -> None:
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        expression = "encode(repeat('x',?))" if column == "record_bytes" else "repeat('x',?)"
        c.execute(f"UPDATE {table} SET {column}={expression} WHERE ordinal=0", [size])
    with pytest.raises(ValueError, match="TRANSFER_BOUND"):
        read(target, result)


def test_independent_aggregate_scalar_preflight(tmp_path: Path) -> None:
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        for i in range(14):
            c.execute(
                f"INSERT INTO {table} SELECT ?,ordinal,record_id,evidence_id,run_id,ts,symbol,"
                "plugin,available,payload_json,record_bytes,source_observation_id,recorded_at "
                f"FROM {table} WHERE revision_id=? AND ordinal=0",
                [f"orphan-{i}", result["revision_id"]],
            )
        c.execute(f"UPDATE {table} SET payload_json=repeat('x',65536)")
    with pytest.raises(ValueError, match="TRANSFER_BOUND"):
        read(target, result)


def test_source_wall_fields_never_change_with_sql_session_timezone(tmp_path: Path) -> None:
    target = prepared(tmp_path)
    result = persist(target)
    original = read(target, result)
    with duckdb.connect(str(target[2]), read_only=True) as c:
        c.execute("SET TimeZone='Asia/Kolkata'")
        assert (
            store.read_decision_evidence_silver(
                c,
                revision_id=result["revision_id"],
                expected_recording_fingerprint=result["recording_fingerprint"],
            )
            == original
        )
        table = store.common.name(c, "silver", store.DOMAIN[2])
        clocks = c.execute(f"SELECT ts FROM {table} ORDER BY ordinal").fetchall()
        assert all(row[0].tzinfo is None for row in clocks)
        assert all(len(store.codec.wall_fields(row[0])) == 26 for row in clocks)


def test_retained_bronze_and_current_legacy_equality_are_distinct(tmp_path: Path) -> None:
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[0])) as c:
        table = store.common.name(c, "main", store.codec.TABLE)
        c.execute(f"UPDATE {table} SET available=NOT available")
    assert read(target, result) == read(target, result, "bronze")
    with pytest.raises(ValueError, match="CURRENT_LEGACY"):
        read(target, result, "source")
    with duckdb.connect(str(target[1])) as c:
        table = store.common.name(c, "medallion_audit", "job_events")
        c.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    assert len(read(target, result)) == 3
    with pytest.raises(ValueError):
        read(target, result, "bronze")


def test_readonly_no_reinitialization_and_live_alias_parent(tmp_path: Path) -> None:
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        with pytest.raises(ValueError, match="READONLY"):
            store.read_decision_evidence_silver(
                c,
                revision_id=result["revision_id"],
                expected_recording_fingerprint=result["recording_fingerprint"],
            )
        with pytest.raises(ValueError, match="EMPTY"):
            store.initialize_decision_evidence_silver(c)
        alias = c.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                store.persist_decision_evidence_silver(
                    c,
                    alias,
                    pins=target[3],
                    expected_context_sha256=target[4],
                    actor_id="synthetic",
                    code_revision="a" * 40,
                )
            assert c.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()


def test_context_bound_before_decode(tmp_path: Path) -> None:
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[1])
        c.execute(f"UPDATE {table} SET context=encode(repeat('x',?))", [store.MAX_CONTEXT + 1])
    with pytest.raises(ValueError, match="UNBOUNDED"):
        read(target, result)


def test_actual_complete_1000_row_boundary(tmp_path: Path) -> None:
    from datetime import timedelta

    legacy, bronze, silver = (tmp_path / f"{n}.duckdb" for n in ("legacy", "bronze", "silver"))
    _source(legacy)
    with duckdb.connect(str(legacy)) as c:
        table = store.common.name(c, "main", store.codec.TABLE)
        c.execute(f"DELETE FROM {table}")
        c.executemany(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?)",
            [
                [f"E-{i}", "run", WALL + timedelta(microseconds=i), "S", "P", bool(i % 2), OPAQUE]
                for i in range(1000)
            ],
        )
    with (
        duckdb.connect(str(legacy), read_only=True) as legacy_connection,
        duckdb.connect(str(bronze)) as b,
    ):
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = store.source.capture_decision_evidence(legacy_connection, source_label="fixture")
        br = store.source.preserve_decision_evidence(
            legacy_connection,
            b,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=IMPORT_AT,
            actor_id="synthetic",
            code_revision="a" * 40,
        )
    pins = store.DecisionEvidenceBronzePins(
        br["source_label"],
        br["snapshot_id"],
        br["capture_event_id"],
        br["envelope_hash"],
        br["recording_fingerprint"],
    )
    with duckdb.connect(str(bronze), read_only=True) as b:
        context = store.observe_decision_evidence_bronze(b, pins=pins)
    with duckdb.connect(str(silver)) as s:
        store.initialize_decision_evidence_silver(s)
    target = legacy, bronze, silver, pins, store.codec.sha(context)
    result = persist(target)
    assert len(read(target, result, "source")) == result["row_count"] == 1000
