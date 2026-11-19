"""Synthetic SQL read-boundary tests on real DuckDB; NOT native audit/writer E2E."""

from datetime import UTC, datetime

import duckdb
import pytest
from test_policy_checkpoint_record import record

from nse_quant.data_platform.policy_checkpoint_record import canonical, series_id
from nse_quant.data_platform.policy_checkpoint_store import (
    COMMAND,
    DEFINITION,
    CheckpointReviewRequired,
    _name,
    read_policy_checkpoint,
)


@pytest.fixture
def sql_fixture(tmp_path):
    # Minimal SQL fixtures exercise the reader only, not AuditLedger or policy verification.
    with duckdb.connect(str(tmp_path / "policy_checkpoint.duckdb")) as conn:
        conn.execute('CREATE SCHEMA "policy_checkpoint"')
        conn.execute('CREATE SCHEMA "medallion_audit"')
        for schema in ("policy_checkpoint", "medallion_audit"):
            name = _name(conn, schema, "schema_versions")
            conn.execute(f"CREATE TABLE {name} (version INTEGER)")
            conn.execute(f"INSERT INTO {name} VALUES (1)")
        conn.execute(
            f"CREATE TABLE {_name(conn, 'policy_checkpoint', 'definitions')} "
            "(version INTEGER,definition_json VARCHAR)"
        )
        conn.execute(
            f"INSERT INTO {_name(conn, 'policy_checkpoint', 'definitions')} VALUES (1,?)",
            [DEFINITION],
        )
        conn.execute(
            f"CREATE TABLE {_name(conn, 'policy_checkpoint', 'records')} "
            "(checkpoint_id VARCHAR,series_id VARCHAR,record_json VARCHAR,"
            "first_job_id VARCHAR,recorded_at TIMESTAMPTZ)"
        )
        conn.execute(
            f"CREATE TABLE {_name(conn, 'policy_checkpoint', 'attempts')} "
            "(job_id VARCHAR,series_id VARCHAR,checkpoint_id VARCHAR)"
        )
        conn.execute(
            f"CREATE TABLE {_name(conn, 'medallion_audit', 'jobs')} "
            "(job_id VARCHAR,parent_job_id VARCHAR,command_name VARCHAR,"
            "config_hash VARCHAR,created_at TIMESTAMPTZ,actor_id VARCHAR,"
            "code_revision VARCHAR,scope_ref VARCHAR)"
        )
        conn.execute(
            f"CREATE TABLE {_name(conn, 'medallion_audit', 'job_events')} "
            "(job_id VARCHAR,event_index INTEGER,state VARCHAR,"
            "recorded_at TIMESTAMPTZ,reason_code VARCHAR)"
        )
        yield conn


def read(conn):
    return read_policy_checkpoint(conn, policy_id="TEST", governance_key_sha256="a" * 64)


def test_empty_snapshot_quoted_catalog_equal_schema(sql_fixture):
    value = read(sql_fixture)
    assert value.head is None
    assert not value.policy_currentness_verified
    assert not value.policy_authority_authenticated


def test_rows_without_origin_are_not_checkpoint_success(sql_fixture):
    from dataclasses import asdict

    item = record()
    sql_fixture.execute(
        f"INSERT INTO {_name(sql_fixture, 'policy_checkpoint', 'records')} VALUES (?,?,?,?,?)",
        [item.checkpoint_id, item.series_id, canonical(asdict(item)), "missing", datetime.now(UTC)],
    )
    with pytest.raises(CheckpointReviewRequired, match="ORIGIN_NOT_LINKED"):
        read(sql_fixture)


def test_incomplete_scoped_job_blocks_even_without_domain_rows(sql_fixture):
    scope = series_id("TEST", "a" * 64)
    sql_fixture.execute(
        f"INSERT INTO {_name(sql_fixture, 'medallion_audit', 'jobs')} VALUES (?,?,?,?,?,?,?,?)",
        ["job", None, COMMAND, "b" * 64, datetime.now(UTC), "synthetic", "synthetic", scope],
    )
    sql_fixture.execute(
        f"INSERT INTO {_name(sql_fixture, 'medallion_audit', 'job_events')} VALUES (?,?,?,?,?)",
        ["job", 1, "PLANNED", datetime.now(UTC), None],
    )
    with pytest.raises(CheckpointReviewRequired, match="AUDIT_OBLIGATION"):
        read(sql_fixture)


def test_foreign_table_refuses_dedicated_store(sql_fixture):
    sql_fixture.execute('CREATE TABLE "foreign" (x INTEGER)')
    with pytest.raises(ValueError, match="DEDICATED"):
        read(sql_fixture)


def append_sql_record(conn, item, job):
    from dataclasses import asdict

    clock = datetime.now(UTC)
    conn.execute(
        f"INSERT INTO {_name(conn, 'policy_checkpoint', 'records')} VALUES (?,?,?,?,?)",
        [item.checkpoint_id, item.series_id, canonical(asdict(item)), job, clock],
    )
    conn.execute(
        f"INSERT INTO {_name(conn, 'policy_checkpoint', 'attempts')} VALUES (?,?,?)",
        [job, item.series_id, item.checkpoint_id],
    )
    conn.execute(
        f"INSERT INTO {_name(conn, 'medallion_audit', 'jobs')} VALUES (?,?,?,?,?,?,?,?)",
        [job, None, COMMAND, item.checkpoint_id, clock, "synthetic", "synthetic", item.series_id],
    )
    for index, state in enumerate(("PLANNED", "RUNNING", "SUCCEEDED"), 1):
        events = _name(conn, "medallion_audit", "job_events")
        conn.execute(f"INSERT INTO {events} VALUES (?,?,?,?,?)", [job, index, state, clock, None])


def test_synthetic_success_timezone_is_instant_based(sql_fixture):
    append_sql_record(sql_fixture, record(), "job")
    before = read(sql_fixture)
    assert before.head.checkpoint_id == record().checkpoint_id
    sql_fixture.execute("SET TimeZone='Asia/Kolkata'")
    assert read(sql_fixture).evidence_fingerprint == before.evidence_fingerprint


def test_synthetic_fork_is_not_latest_success_wins(sql_fixture):
    from dataclasses import replace

    first = record()
    append_sql_record(sql_fixture, first, "j1")
    append_sql_record(sql_fixture, replace(first, tip_sha256="e" * 64), "j2")
    with pytest.raises(CheckpointReviewRequired, match="FORK_OR_UNLINKED"):
        read(sql_fixture)


def test_later_synthetic_success_cannot_repair_failed_origin(sql_fixture):
    append_sql_record(sql_fixture, record(), "job")
    sql_fixture.execute(
        f"UPDATE {_name(sql_fixture, 'medallion_audit', 'job_events')} "
        "SET state='FAILED',reason_code='SYNTHETIC' WHERE event_index=3"
    )
    with pytest.raises(CheckpointReviewRequired, match="AUDIT_OBLIGATION"):
        read(sql_fixture)


def test_unlinked_synthetic_attempt_blocks(sql_fixture):
    scope = series_id("TEST", "a" * 64)
    sql_fixture.execute(
        f"INSERT INTO {_name(sql_fixture, 'policy_checkpoint', 'attempts')} VALUES ('missing',?,?)",
        [scope, "e" * 64],
    )
    with pytest.raises(CheckpointReviewRequired, match="ATTEMPT_LINK"):
        read(sql_fixture)
