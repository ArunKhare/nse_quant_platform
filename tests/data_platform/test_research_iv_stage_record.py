"""Synthetic record consistency and real SQL audit-obligation tests; NOT native proof."""

from datetime import UTC, datetime, timedelta, timezone

import duckdb
import pytest

from nse_quant.data_platform import research_iv_first_stage as store
from nse_quant.data_platform import research_iv_stage_record as record


def synthetic_record(tmp_path):
    return dict(
        version=record.VERSION,
        definition=list(record.DEFINITION),
        pins=["a" * 64, "b" * 64, "c" * 64, "d" * 64],
        artifact_root=str(tmp_path / "artifacts"),
        artifact_name="c" * 64 + ".research-iv.json",
        artifact_bytes=10,
        before_sha256="e" * 64,
        after_sha256="e" * 64,
        status="RESEARCH_IV_STAGE_RECORDED_NOT_PUBLISHED",
        canonical_contract_id=None,
        event_ts=None,
        published_at=None,
        **{key: False for key in record.FLAGS},
    )


def test_record_roundtrip_content_id_and_exact_scope(tmp_path):
    value = synthetic_record(tmp_path)
    raw = record.canonical(value)
    assert record.decode(raw) == value
    assert record.build_id(raw) == record.sha(raw.encode())
    original = record.scope(tuple(value["pins"]), value["artifact_root"])
    changed = list(value["pins"])
    changed[-1] = "f" * 64
    assert record.scope(tuple(changed), value["artifact_root"]) != original
    value["artifact_bytes"] = 11
    assert record.build_id(record.canonical(value)) != record.build_id(raw)


@pytest.mark.parametrize("field", record.FLAGS, ids=list(record.FLAGS))
def test_self_rehashed_authority_escalation_not_allowed(tmp_path, field):
    value = synthetic_record(tmp_path)
    value[field] = True
    with pytest.raises(ValueError):
        record.build_id(record.canonical(value))


@pytest.mark.parametrize(
    "change",
    [
        {"extra": True},
        {"version": "unknown@2"},
        {"artifact_bytes": True},
        {"artifact_bytes": 4194305},
        {"after_sha256": "f" * 64},
        {"artifact_name": "../unsafe"},
        {"canonical_contract_id": "invented"},
        {"event_ts": "invented"},
        {"published_at": "invented"},
        {"status": "ELIGIBLE"},
        {"pins": ["a" * 64]},
        {"definition": []},
    ],
    ids=[
        "extra",
        "version",
        "bool",
        "size",
        "drift",
        "name",
        "identity",
        "event",
        "published",
        "status",
        "pins",
        "definition",
    ],
)
def test_invalid_record_cannot_be_rehashed_into_acceptance(tmp_path, change):
    value = synthetic_record(tmp_path)
    value.update(change)
    with pytest.raises(ValueError):
        record.build_id(record.canonical(value))


def test_strict_json_and_record_bounds(tmp_path, monkeypatch):
    raw = record.canonical(synthetic_record(tmp_path))
    for changed in (raw + "\n", " " + raw, '{"a":1,"a":2}', '{"a":NaN}', "[]", "{}{}"):
        with pytest.raises(ValueError):
            record.decode(changed)
    monkeypatch.setattr(record, "MAX_RECORD_BYTES", 1)
    with pytest.raises(ValueError, match="BYTE_LIMIT"):
        record.decode(raw)


@pytest.fixture
def empty_sql(tmp_path):
    conn = duckdb.connect(str(tmp_path / "synthetic-stage.duckdb"))
    catalog = conn.execute("SELECT current_database()").fetchone()
    assert catalog is not None
    quoted = '"' + str(catalog[0]).replace('"', '""') + '"'
    conn.execute(f'CREATE SCHEMA {quoted}."gold"')
    conn.execute(f'CREATE SCHEMA {quoted}."medallion_audit"')
    conn.execute(f"CREATE TABLE {store._name(conn, 'gold', store.TABLES[0])} (version INTEGER)")
    conn.execute(f"INSERT INTO {store._name(conn, 'gold', store.TABLES[0])} VALUES (1)")
    conn.execute(
        f"CREATE TABLE {store._name(conn, 'gold', store.TABLES[1])} (build_id VARCHAR,"
        "scope_id VARCHAR,record_json VARCHAR,feature_version VARCHAR,first_job_id VARCHAR,"
        "recorded_at TIMESTAMPTZ,event_ts TIMESTAMPTZ,published_at TIMESTAMPTZ)"
    )
    conn.execute(
        f"CREATE TABLE {store._name(conn, 'gold', store.TABLES[2])} "
        "(job_id VARCHAR,scope_id VARCHAR,build_id VARCHAR)"
    )
    conn.execute(
        f"CREATE TABLE {store._name(conn, 'medallion_audit', 'schema_versions')} (version INTEGER)"
    )
    versions = store._name(conn, "medallion_audit", "schema_versions")
    conn.execute(f"INSERT INTO {versions} VALUES (1)")
    conn.execute(
        f"CREATE TABLE {store._name(conn, 'medallion_audit', 'dataset_contracts')} ("
        "dataset_name VARCHAR,contract_version VARCHAR,fingerprint VARCHAR,"
        "contract_json VARCHAR,registered_at TIMESTAMPTZ)"
    )
    conn.execute(
        f"CREATE TABLE {store._name(conn, 'medallion_audit', 'jobs')} ("
        "job_id VARCHAR,parent_job_id VARCHAR,command_name VARCHAR,scope_ref VARCHAR,"
        "config_hash VARCHAR,created_at TIMESTAMPTZ,actor_id VARCHAR,"
        "code_revision VARCHAR)"
    )
    conn.execute(
        f"CREATE TABLE {store._name(conn, 'medallion_audit', 'job_events')} ("
        "job_id VARCHAR,event_index INTEGER,state VARCHAR,recorded_at TIMESTAMPTZ,"
        "reason_code VARCHAR)"
    )
    yield conn
    conn.close()


def insert_job(conn, states):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    conn.execute(
        f"INSERT INTO {store._name(conn, 'medallion_audit', 'jobs')} VALUES (?,NULL,?,?,?,?,?,?)",
        [
            "synthetic-job",
            store.COMMAND,
            "a" * 64,
            record.sha(record.canonical(record.DEFINITION).encode()),
            now,
            "test",
            "test",
        ],
    )
    for index, state in enumerate(states, 1):
        conn.execute(
            f"INSERT INTO {store._name(conn, 'medallion_audit', 'job_events')} "
            "VALUES (?,?,?,?,NULL)",
            ["synthetic-job", index, state, now],
        )


def test_empty_sql_snapshot_is_read_only_and_deterministic(empty_sql):
    first = store._transaction_snapshot(empty_sql)
    assert first[0] == []
    assert first == store._transaction_snapshot(empty_sql)


@pytest.mark.parametrize(
    "states",
    [
        ("PLANNED",),
        ("PLANNED", "RUNNING"),
        ("PLANNED", "RUNNING", "FAILED"),
        ("PLANNED", "RUNNING", "SUCCEEDED"),
        ("PLANNED", "CANCELLED"),
    ],
    ids=["planned", "running", "failed", "unlinked-success", "cancelled"],
)
def test_all_unlinked_obligations_block_before_any_status_filter(empty_sql, states):
    insert_job(empty_sql, states)
    with pytest.raises(store.IvFirstStageReviewRequired, match="OBLIGATION"):
        store._transaction_snapshot(empty_sql)
    assert empty_sql.execute("SELECT 1").fetchone() == (1,)


def test_only_explicit_active_job_is_allowed_with_exact_scope(empty_sql):
    insert_job(empty_sql, ("PLANNED", "RUNNING"))
    rows, fingerprint = store._snapshot(
        empty_sql,
        active_job="synthetic-job",
        active_scope="a" * 64,
    )
    assert rows == [] and len(fingerprint) == 64
    with pytest.raises(store.IvFirstStageReviewRequired):
        store._snapshot(empty_sql, active_job="synthetic-job", active_scope="b" * 64)


def test_orphan_events_are_not_hidden_by_joins(empty_sql):
    empty_sql.execute(
        f"INSERT INTO {store._name(empty_sql, 'medallion_audit', 'job_events')} "
        "VALUES ('missing',1,'PLANNED',?,NULL)",
        [datetime.now(UTC)],
    )
    with pytest.raises(store.IvFirstStageReviewRequired, match="ORPHAN_AUDIT"):
        store._transaction_snapshot(empty_sql)


def test_job_bound_is_enforced_before_event_materialization(empty_sql, monkeypatch):
    insert_job(empty_sql, ("PLANNED",))
    monkeypatch.setattr(store, "MAX_JOBS", 0)
    with pytest.raises(store.IvFirstStageReviewRequired, match="PROFILE_LIMIT"):
        store._transaction_snapshot(empty_sql)


def test_reader_does_not_initialize(tmp_path):
    conn = duckdb.connect(str(tmp_path / "empty.duckdb"))
    try:
        # _transaction_snapshot is the reader's first operation, before artifact/codec work.
        with pytest.raises(duckdb.Error):
            store._transaction_snapshot(conn)
        assert conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_catalog=current_database()"
        ).fetchone() == (0,)
    finally:
        conn.close()


def test_aware_clock_is_converted_not_relabelled():
    clock = datetime(2026, 1, 1, 5, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert store._instant(clock) == "2026-01-01T00:00:00+00:00"
    with pytest.raises(ValueError):
        store._instant(datetime(2026, 1, 1))
