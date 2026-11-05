"""Actual schema + explicit synthetic SQL -> native Bronze -> persisted snapshot Silver.

Uses accepted SQL-seeded fixture; does NOT claim unretrieved legacy writer execution.
"""

from dataclasses import replace
from datetime import timedelta

import duckdb
import pytest
from test_legacy_evidence_snapshot_bronze import AT, IMPORT_AT, record, seed

from nse_quant.data_platform import legacy_evidence_snapshot_silver_store as store
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore


def prepared(tmp_path):
    legacy, bronze, result = record(tmp_path)
    pins = store.EvidenceSnapshotBronzePins(
        result["source_label"],
        result["snapshot_id"],
        result["capture_event_id"],
        result["envelope_hash"],
        result["recording_fingerprint"],
    )
    silver = tmp_path / "silver.duckdb"  # Real catalog/schema collision preserved.
    with duckdb.connect(str(bronze), read_only=True) as b:
        context = store.observe_evidence_snapshot_bronze(b, pins=pins)
    with duckdb.connect(str(silver)) as s:
        store.initialize_evidence_snapshot_silver(s)
    return legacy, bronze, silver, pins, store.codec.sha(context)


def persist(target, **changes):
    args = dict(
        pins=target[3],
        expected_context_sha256=target[4],
        actor_id="synthetic",
        code_revision="a" * 40,
    )
    args.update(changes)
    with duckdb.connect(str(target[1]), read_only=True) as b, duckdb.connect(str(target[2])) as s:
        return store.persist_evidence_snapshot_silver(b, s, **args)


def read(target, result, mode="retained"):
    args = dict(
        revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(target[2]), read_only=True) as s:
        if mode == "retained":
            return store.read_evidence_snapshot_silver(s, **args)
        with duckdb.connect(str(target[1]), read_only=True) as b:
            if mode == "bronze":
                return store.revalidate_evidence_snapshot_silver(b, s, **args)
            with duckdb.connect(str(target[0]), read_only=True) as legacy:
                return store.revalidate_evidence_snapshot_silver_source(legacy, b, s, **args)


def test_actual_sql_native_bronze_silver_chain_all_fields_nulls_and_instants(tmp_path):
    target = prepared(tmp_path)
    result = persist(target)
    rows = read(target, result)
    assert rows == read(target, result, "bronze") == read(target, result, "source")
    assert len(rows) == result["row_count"] == 3
    with (
        duckdb.connect(str(target[0]), read_only=True) as legacy,
        duckdb.connect(str(target[1]), read_only=True) as bronze,
        duckdb.connect(str(target[2]), read_only=True) as silver,
    ):
        assert rows == store.source.read_evidence_snapshot_bronze(bronze, **target[3].reader_args())
        table = store.common.name(legacy, "main", store.codec.TABLE)
        originals = legacy.execute(
            f"SELECT run_id,ts,symbol,plugin_name,CAST(payload_json AS VARCHAR) FROM {table}"
        ).fetchall()
        by_key = {
            (r[0], store.codec.encode_cell(r[1], "TIMESTAMP WITH TIME ZONE"), r[3]): r
            for r in originals
        }
        table = store.common.name(silver, "silver", store.DOMAIN[2])
        scalars = silver.execute(
            f"SELECT run_id,ts,symbol,plugin_name,payload_json FROM {table} ORDER BY ordinal"
        ).fetchall()
        for raw, actual in zip(rows, scalars, strict=True):
            doc = store.codec.parse(raw, store.MAX_RECORD)
            fields = doc["stored_fields"]
            key = fields["run_id"], fields["ts"], fields["plugin_name"]
            assert fields == {
                n: store.codec.encode_cell(v, kind)
                for v, (n, kind) in zip(by_key[key], store.SOURCE_SCHEMA, strict=True)
            }
            assert fields == {
                n: store.codec.encode_cell(v, kind)
                for v, (n, kind) in zip(actual, store.SOURCE_SCHEMA, strict=True)
            }
            assert actual[1].tzinfo is not None
            assert doc["stored_ts_instant"] == fields["ts"]
            assert doc["original_availability_at"] is None
            assert not doc["payload_interpreted"]
            assert not doc["payload_json_validation_reperformed"]
            assert not doc["native_decision_replayed"]
            assert not doc["decision_eligibility_asserted"]
        assert any(r[2] is None for r in scalars)
        assert any(r[4] is None for r in scalars)
        assert any(r[4] == "null" for r in scalars)


@pytest.mark.parametrize(
    "column,value",
    [
        ("run_id", "'changed'"),
        ("ts", "ts+INTERVAL '1 microsecond'"),
        ("symbol", "'changed'"),
        ("plugin_name", "'changed'"),
        ("payload_json", "'changed'"),
        ("record_id", "'bad'"),
        ("record_bytes", "'bad'::BLOB"),
        ("source_observation_id", "'bad'"),
    ],
    ids=["run", "instant", "symbol", "plugin", "opaque-text", "hash", "bytes", "source-event"],
)
def test_all_materialized_scalar_and_record_corruption(tmp_path, column, value):
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
    ids=["row", "attempt", "audit", "contract", "definition", "clock"],
)
def test_original_recording_and_coverage(tmp_path, case):
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
    ["source_label", "snapshot_id", "envelope_hash", "recording_fingerprint"],
    ids=["label", "snapshot", "envelope", "recording"],
)
def test_review_changes_cannot_heal_same_native_event(tmp_path, field):
    target = prepared(tmp_path)
    bad = replace(target[3], **{field: "other" if field == "source_label" else "d" * 64})
    assert bad.scope_id == target[3].scope_id
    with pytest.raises(ValueError):
        persist(target, pins=bad)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        persist(target)


def test_bad_context_review_cannot_heal(tmp_path):
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
def test_extra_scoped_jobs_cannot_hide(tmp_path, state):
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


def test_first_write_before_actual_bronze_reader(tmp_path, monkeypatch):
    target = prepared(tmp_path)
    persist(target)

    def forbidden(*args, **kwargs):
        raise AssertionError("source must not be read")

    monkeypatch.setattr(store.source, "read_evidence_snapshot_bronze", forbidden)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        persist(target)


def test_same_event_other_revision_and_orphans_not_adopted(tmp_path):
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        c.execute(
            f"INSERT INTO {table} SELECT ?,ordinal,record_id,run_id,ts,symbol,plugin_name,"
            f"payload_json,record_bytes,source_observation_id,recorded_at "
            f"FROM {table} WHERE ordinal=0",
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
        persist(target)


def test_actual_sql_domain_failure_rolls_back_set_rows_and_link(tmp_path):
    target = prepared(tmp_path)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[3])
        c.execute(f"ALTER TABLE {table} ADD COLUMN synthetic_failure INTEGER DEFAULT 0")
    with pytest.raises(duckdb.Error):
        persist(target)
    with duckdb.connect(str(target[2]), read_only=True) as c:
        for n in store.DOMAIN[1:]:
            table = store.common.name(c, "silver", n)
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        persist(target)


def test_final_audit_failure_after_commit_cannot_read_or_adopt(tmp_path, monkeypatch):
    target = prepared(tmp_path)
    original = AuditLedger.transition

    def fail(self, job, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT")
        return original(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail)
    with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
        persist(target)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with duckdb.connect(str(target[2]), read_only=True) as c:
        table = store.common.name(c, "silver", store.DOMAIN[1])
        row = c.execute(f"SELECT revision_id FROM {table}").fetchone()
        assert row is not None
        with pytest.raises(ValueError, match="AUDIT_NOT_VERIFIED"):
            store.read_evidence_snapshot_silver(
                c, revision_id=row[0], expected_recording_fingerprint="a" * 64
            )
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        persist(target)


def test_second_actual_native_reader_failure_no_partial_success(tmp_path, monkeypatch):
    target = prepared(tmp_path)
    original = store.source.read_evidence_snapshot_bronze
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_BRONZE_READ")
        return original(*args, **kwargs)

    monkeypatch.setattr(store.source, "read_evidence_snapshot_bronze", observe)
    with pytest.raises(RuntimeError, match="SECOND_BRONZE_READ"):
        persist(target)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        persist(target)


@pytest.mark.parametrize(
    "column,size",
    [
        ("record_bytes", 524289),
        ("record_bytes", 4194305),
        ("payload_json", 65537),
        ("symbol", 65537),
    ],
    ids=["record-cell", "record-total", "payload-cell", "symbol-cell"],
)
def test_independent_sql_transfer_guards(tmp_path, column, size):
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        value = "encode(repeat('x',?))" if column == "record_bytes" else "repeat('x',?)"
        c.execute(f"UPDATE {table} SET {column}={value} WHERE ordinal=0", [size])
    with pytest.raises(ValueError, match="TRANSFER_BOUND"):
        read(target, result)


def test_aggregate_scalar_budget_is_independent(tmp_path):
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        for i in range(14):
            c.execute(
                f"INSERT INTO {table} SELECT ?,ordinal,record_id,run_id,ts,symbol,plugin_name,"
                f"payload_json,record_bytes,source_observation_id,recorded_at "
                f"FROM {table} WHERE revision_id=? AND ordinal=0",
                [f"orphan-{i}", result["revision_id"]],
            )
        c.execute(f"UPDATE {table} SET payload_json=repeat('x',65536)")
    with pytest.raises(ValueError, match="TRANSFER_BOUND"):
        read(target, result)


def test_source_type_and_nullability_drift_rejected(tmp_path):
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        c.execute(f"UPDATE {table} SET symbol=coalesce(symbol, 'S')")
        c.execute(f"ALTER TABLE {table} ALTER COLUMN symbol SET NOT NULL")
    with pytest.raises(ValueError, match="SCHEMA_DRIFT"):
        read(target, result)


def test_sql_null_and_json_null_cannot_be_silently_exchanged(tmp_path):
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        c.execute(f"UPDATE {table} SET payload_json='null' WHERE payload_json IS NULL")
    with pytest.raises(ValueError, match="RECOMPUTATION"):
        read(target, result)


def test_timezone_readonly_no_reinit_and_live_alias_parent(tmp_path):
    target = prepared(tmp_path)
    result = persist(target)
    original = read(target, result)
    args = dict(
        revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(target[2]), read_only=True) as c:
        c.execute("SET TimeZone='Asia/Kolkata'")
        assert store.read_evidence_snapshot_silver(c, **args) == original
    with duckdb.connect(str(target[2])) as c:
        with pytest.raises(ValueError, match="READONLY"):
            store.read_evidence_snapshot_silver(c, **args)
        with pytest.raises(ValueError, match="EMPTY"):
            store.initialize_evidence_snapshot_silver(c)
        alias = c.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                store.persist_evidence_snapshot_silver(
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


def test_retained_current_bronze_and_current_legacy_are_distinct(tmp_path):
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[0])) as c:
        table = store.common.name(c, "main", store.codec.TABLE)
        c.execute(f"UPDATE {table} SET symbol='changed'")
    assert read(target, result) == read(target, result, "bronze")
    with pytest.raises(ValueError, match="CURRENT_LEGACY"):
        read(target, result, "source")
    with duckdb.connect(str(target[1])) as c:
        table = store.common.name(c, "medallion_audit", "job_events")
        c.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    assert len(read(target, result)) == 3
    with pytest.raises(ValueError):
        read(target, result, "bronze")


def test_context_bound_before_parse(tmp_path):
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[1])
        c.execute(f"UPDATE {table} SET context=encode(repeat('x',?))", [store.MAX_CONTEXT + 1])
    with pytest.raises(ValueError, match="UNBOUNDED"):
        read(target, result)


def test_sql_key_is_run_time_plugin_not_symbol(tmp_path):
    target = prepared(tmp_path)
    result = persist(target)
    with duckdb.connect(str(target[2])) as c:
        table = store.common.name(c, "silver", store.DOMAIN[2])
        with pytest.raises(duckdb.ConstraintException):
            c.execute(
                f"INSERT INTO {table} SELECT revision_id,100,record_id,run_id,ts,'other',"
                f"plugin_name,payload_json,record_bytes,source_observation_id,recorded_at "
                f"FROM {table} WHERE ordinal=0"
            )
    assert len(read(target, result)) == 3


def test_complete_1000_row_boundary_actual_native_chain(tmp_path):
    legacy, bronze, silver = (tmp_path / f"{n}.duckdb" for n in ("legacy", "bronze", "silver"))
    seed(legacy)
    with duckdb.connect(str(legacy)) as c:
        table = store.common.name(c, "main", store.codec.TABLE)
        c.execute(f"DELETE FROM {table}")
        c.executemany(
            f"INSERT INTO {table} VALUES (?,?,?,?,CAST(? AS JSON))",
            [
                [
                    "R",
                    AT + timedelta(microseconds=i),
                    None if i % 2 else "S",
                    f"P-{i}",
                    None if i % 3 == 0 else "null",
                ]
                for i in range(1000)
            ],
        )
    with (
        duckdb.connect(str(legacy), read_only=True) as legacy_connection,
        duckdb.connect(str(bronze)) as b,
    ):
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = store.source.capture_evidence_snapshots(
            legacy_connection, source_label="fixture"
        )
        br = store.source.preserve_evidence_snapshots(
            legacy_connection,
            b,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=IMPORT_AT,
            actor_id="synthetic",
            code_revision="a" * 40,
        )
    pins = store.EvidenceSnapshotBronzePins(
        br["source_label"],
        br["snapshot_id"],
        br["capture_event_id"],
        br["envelope_hash"],
        br["recording_fingerprint"],
    )
    with duckdb.connect(str(bronze), read_only=True) as b:
        context = store.observe_evidence_snapshot_bronze(b, pins=pins)
    with duckdb.connect(str(silver)) as s:
        store.initialize_evidence_snapshot_silver(s)
    target = legacy, bronze, silver, pins, store.codec.sha(context)
    result = persist(target)
    assert len(read(target, result, "source")) == result["row_count"] == 1000
