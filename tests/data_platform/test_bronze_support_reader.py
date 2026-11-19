"""Real DuckDB evidence checking on synthetic rows, NOT native acquisition or identity E2E."""

import hashlib
from dataclasses import replace
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import bronze_support_reader as reader

T = datetime(2026, 1, 1, tzinfo=UTC)


def hashed(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture(
    params=[
        pytest.param("bronze", id="catalog-schema-collision"),
        pytest.param("odd'catalog\"name", id="quoted-catalog"),
    ]
)
def support_db(tmp_path, request):
    connection = duckdb.connect(":memory:")
    path = str(tmp_path / "source.duckdb").replace("'", "''")

    def quote(value):
        return '"' + value.replace('"', '""') + '"'

    alias = quote(request.param)
    connection.execute(f"ATTACH '{path}' AS {alias}")
    connection.execute(f"USE {alias}")
    connection.execute("CREATE SCHEMA bronze")
    connection.execute("CREATE SCHEMA medallion_audit")

    def name(schema, table):
        return reader._name(connection, schema, table)

    connection.execute(f"CREATE TABLE {name('bronze', 'schema_versions')}(version INTEGER)")
    connection.execute(f"INSERT INTO {name('bronze', 'schema_versions')} VALUES (1)")
    connection.execute(
        f"CREATE TABLE {name('medallion_audit', 'schema_versions')} "
        "(version INTEGER,applied_at TIMESTAMPTZ)"
    )
    connection.execute(
        f"INSERT INTO {name('medallion_audit', 'schema_versions')} VALUES (1,?)", [T]
    )
    event_types = [
        "BIGINT"
        if column == "ingest_sequence"
        else "BLOB"
        if column == "payload"
        else "TIMESTAMPTZ"
        if column in {"received_at", "recorded_at", "exchange_ts"}
        else "VARCHAR"
        for column in reader.EVENT_COLUMNS
    ]
    event_columns = ",".join(
        f'"{c}" {t}' for c, t in zip(reader.EVENT_COLUMNS, event_types, strict=True)
    )
    connection.execute(f"CREATE TABLE {name('bronze', 'event_variants')} ({event_columns})")
    connection.execute(
        f"CREATE TABLE {name('bronze', 'ingest_batches')} "
        "(batch_key VARCHAR,batch_fingerprint VARCHAR,input_file_hash VARCHAR,"
        "input_events BIGINT,inserted_variants BIGINT,exact_retries BIGINT,"
        "conflict_variants BIGINT,last_sequence BIGINT,job_id VARCHAR,"
        "committed_at TIMESTAMPTZ)"
    )
    connection.execute(
        f"CREATE TABLE {name('bronze', 'input_artifacts')} "
        "(artifact_hash VARCHAR,artifact_bytes BLOB,recorded_at TIMESTAMPTZ,"
        "first_job_id VARCHAR)"
    )
    connection.execute(
        f"CREATE TABLE {name('medallion_audit', 'jobs')} "
        "(job_id VARCHAR,parent_job_id VARCHAR,command_name VARCHAR,"
        "actor_id VARCHAR,"
        "scope_ref VARCHAR,code_revision VARCHAR,config_hash VARCHAR,"
        "created_at TIMESTAMPTZ)"
    )
    connection.execute(
        f"CREATE TABLE {name('medallion_audit', 'job_events')} "
        "(job_id VARCHAR,event_index INTEGER,state VARCHAR,recorded_at TIMESTAMPTZ,"
        "reason_code VARCHAR)"
    )
    payload = b"synthetic unsupported identity claim"
    artifact = b"synthetic input artifact: no parsing provenance is implied"
    envelope = dict(
        envelope_version=1,
        source="test",
        capture_session_id="session",
        source_record_id="one",
        received_at=T.isoformat(),
        payload_hash=hashed(payload),
        payload_format="bytes",
        origin_kind="historical_import",
        exchange_ts=None,
        provider_event_id=None,
        instrument_ref=None,
    )
    event_id = hashed(reader._canonical(["test", "session", "one"]).encode())
    envelope_hash = hashed(reader._canonical(envelope).encode())
    event = [
        event_id,
        envelope_hash,
        1,
        "test",
        "session",
        "one",
        T,
        T,
        None,
        payload,
        hashed(payload),
        "bytes",
        "historical_import",
        reader._canonical(envelope),
        "batch-one",
        "origin-job",
    ]
    connection.execute(
        f"INSERT INTO {name('bronze', 'event_variants')} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        event,
    )
    fingerprint = hashed(
        reader._canonical(
            {
                "input_file_hash": hashed(artifact),
                "events": [[event_id, envelope_hash]],
            }
        ).encode()
    )
    connection.execute(
        f"INSERT INTO {name('bronze', 'ingest_batches')} VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            "batch-one",
            fingerprint,
            hashed(artifact),
            1,
            1,
            0,
            0,
            1,
            "origin-job",
            T,
        ],
    )
    connection.execute(
        f"INSERT INTO {name('bronze', 'input_artifacts')} VALUES (?,?,?,?)",
        [hashed(artifact), artifact, T, "origin-job"],
    )
    expected = reader.IngestAuditExpectation("test.ingest@1", "sha256:" + "c" * 64, "d" * 64)
    connection.execute(
        f"INSERT INTO {name('medallion_audit', 'jobs')} VALUES (?,?,?,?,?,?,?,?)",
        [
            "origin-job",
            None,
            expected.command_name,
            "test",
            expected.scope_ref,
            "a331f45",
            expected.config_hash,
            T,
        ],
    )
    for index, state in enumerate(reader.SUCCESS_PATHS[0], start=1):
        connection.execute(
            f"INSERT INTO {name('medallion_audit', 'job_events')} VALUES (?,?,?,?,?)",
            ["origin-job", index, state, T, None],
        )
    support = reader.BronzeSupportPin(
        event_id,
        envelope_hash,
        hashed(payload),
        0,
        len(payload),
        hashed(payload),
    )

    def inspect(pin=None, audit=None):
        return reader.inspect_bronze_support(
            connection,
            support=support if pin is None else pin,
            expected_audit=expected if audit is None else audit,
        )

    yield connection, support, expected, name, inspect
    connection.close()


def test_current_storage_evidence_does_not_authenticate_source_or_identity(support_db):
    _, _, _, _, inspect = support_db
    result = inspect()
    assert result.status == "verified_storage_evidence"
    assert result.current_payload_integrity_verified
    assert result.retained_input_artifact_verified
    assert result.fresh_batch_membership_verified
    assert result.origin_ingest_audit_verified
    assert result.scoped_audit_history_verified
    assert not result.retry_link_coverage_verified
    assert not result.artifact_to_event_semantics_verified
    assert not result.source_acquisition_authenticity_asserted
    assert not result.identity_verified
    assert not result.issuer_authenticated
    assert not result.availability_evidence_verified
    assert not result.historical_validity_asserted
    assert not result.decision_eligibility_asserted


@pytest.mark.parametrize(
    "table,assignment",
    [
        ("event_variants", "payload='bad'::BLOB"),
        ("event_variants", "envelope_json='{}'"),
        ("event_variants", "received_at=NULL"),
        ("ingest_batches", "batch_fingerprint='bad'"),
        ("ingest_batches", "input_events=2"),
        ("ingest_batches", "inserted_variants=0,exact_retries=1"),
        ("ingest_batches", "last_sequence=99"),
        ("input_artifacts", "artifact_bytes='bad'::BLOB"),
        ("input_artifacts", "first_job_id='other-origin'"),
    ],
)
def test_corrupt_or_unsupported_storage_never_verifies(support_db, table, assignment):
    conn, _, _, name, inspect = support_db
    conn.execute(f"UPDATE {name('bronze', table)} SET {assignment}")
    result = inspect()
    assert result.status == "review_required"
    assert not result.scoped_audit_history_verified
    assert not result.identity_verified


def test_later_conflict_blocks_all_variants(support_db):
    conn, _, _, name, inspect = support_db
    table = name("bronze", "event_variants")
    conn.execute(f"INSERT INTO {table} SELECT * FROM {table}")
    assert inspect().status == "review_required"


def test_full_origin_lifecycle_not_later_success_is_required(support_db):
    conn, _, expected, name, inspect = support_db
    events = name("medallion_audit", "job_events")
    conn.execute(f"DELETE FROM {events} WHERE state='SUCCEEDED'")
    jobs = name("medallion_audit", "jobs")
    conn.execute(
        f"INSERT INTO {jobs} VALUES (?,?,?,?,?,?,?,?)",
        [
            "retry-job",
            None,
            expected.command_name,
            "test",
            expected.scope_ref,
            "test",
            expected.config_hash,
            T,
        ],
    )
    for i, state in enumerate(reader.SUCCESS_PATHS[0], start=1):
        conn.execute(f"INSERT INTO {events} VALUES (?,?,?,?,?)", ["retry-job", i, state, T, None])
    result = inspect()
    assert result.status == "review_required"
    assert not result.origin_ingest_audit_verified
    assert "origin-job" in result.audit_obligation_job_ids


def test_failed_scoped_job_preserves_valid_origin_but_blocks_scope_clearance(support_db):
    conn, _, expected, name, inspect = support_db
    jobs, events = name("medallion_audit", "jobs"), name("medallion_audit", "job_events")
    conn.execute(
        f"INSERT INTO {jobs} VALUES (?,?,?,?,?,?,?,?)",
        [
            "failed-job",
            None,
            expected.command_name,
            "test",
            expected.scope_ref,
            "test",
            expected.config_hash,
            T,
        ],
    )
    conn.execute(f"INSERT INTO {events} VALUES (?,?,?,?,?)", ["failed-job", 1, "PLANNED", T, None])
    conn.execute(
        f"INSERT INTO {events} VALUES (?,?,?,?,?)",
        ["failed-job", 2, "FAILED", T, "EXECUTION_ERROR"],
    )
    result = inspect()
    assert result.origin_ingest_audit_verified
    assert not result.scoped_audit_history_verified
    assert result.audit_obligation_job_ids == ("failed-job",)


def test_exact_expected_metadata_is_required(support_db):
    _, _, expected, _, inspect = support_db
    result = inspect(audit=replace(expected, config_hash="e" * 64))
    assert result.status == "review_required"


def test_fragment_and_actual_payload_bounds(support_db):
    _, support, _, _, inspect = support_db
    assert inspect(pin=replace(support, fragment_sha256="f" * 64)).status == "review_required"
    assert inspect(pin=replace(support, byte_end=support.byte_end + 1)).status == "review_required"


def test_session_timezone_and_readonly_observation(support_db):
    conn, support, expected, _, inspect = support_db
    first = inspect()
    conn.execute("SET TimeZone='Asia/Kolkata'")
    assert inspect().evidence_fingerprint == first.evidence_fingerprint
    catalog = conn.execute("SELECT current_database()").fetchone()[0]
    path = next(
        row[2] for row in conn.execute("PRAGMA database_list").fetchall() if row[1] == catalog
    )
    conn.close()
    with duckdb.connect(":memory:") as readonly:
        escaped = path.replace("'", "''")
        quoted = '"' + catalog.replace('"', '""') + '"'
        readonly.execute(f"ATTACH '{escaped}' AS {quoted} (READ_ONLY)")
        readonly.execute(f"USE {quoted}")
        result = reader.inspect_bronze_support(readonly, support=support, expected_audit=expected)
        assert result.evidence_fingerprint == first.evidence_fingerprint


def test_query_failure_propagates_without_fabricated_rejection(support_db):
    conn, _, _, name, inspect = support_db
    conn.execute(f"DROP TABLE {name('bronze', 'ingest_batches')}")
    with pytest.raises(duckdb.Error):
        inspect()


@pytest.mark.parametrize(
    "states",
    [
        ("SUCCEEDED",),
        ("PLANNED", "SUCCEEDED"),
        ("PLANNED", "RUNNING", "SUCCEEDED", "FAILED"),
        ("PLANNED", "RUNNING", "STAGED", "VALIDATED", "PUBLISHED", "CANCELLED"),
    ],
)
def test_invalid_lifecycles_not_rescued_by_success(states):
    with pytest.raises(reader.SupportReviewRequired):
        reader._lifecycle([(i + 1, state, T, None) for i, state in enumerate(states)])


def test_default_cli_no_io_no_execution_import(tmp_path, monkeypatch, capsys):
    import builtins

    from nse_quant.data_platform.bronze_support_cli import main

    original = builtins.__import__

    def guarded(module, *args, **kwargs):
        if module in {"duckdb", "nse_quant.data_platform.bronze_support_reader"}:
            raise AssertionError("Plan imported execution")
        return original(module, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert (
        main(
            [
                "--bronze-db",
                str(tmp_path / "missing.duckdb"),
                "--request-file",
                str(tmp_path / "request.json"),
            ]
        )
        == 0
    )
    assert list(tmp_path.iterdir()) == []
    assert "PLANNED" in capsys.readouterr().out


@pytest.mark.parametrize("constant", ["MAX_BATCH_BYTES", "MAX_BATCH_EVENTS", "MAX_JOBS"])
def test_capacity_never_becomes_partial_success(support_db, monkeypatch, constant):
    _, _, _, _, inspect = support_db
    monkeypatch.setattr(reader, constant, 0)
    result = inspect()
    assert result.status == "review_required"
    assert not result.scoped_audit_history_verified


def test_oversized_actor_does_not_turn_into_accepted_null(support_db):
    conn, _, _, name, inspect = support_db
    conn.execute(f"UPDATE {name('medallion_audit', 'jobs')} SET actor_id=?", ["x" * 4097])
    assert inspect().status == "review_required"


def test_full_staged_lifecycle_is_supported_without_skipping_phases(support_db):
    conn, _, _, name, inspect = support_db
    table = name("medallion_audit", "job_events")
    conn.execute(f"DELETE FROM {table}")
    for index, state in enumerate(reader.SUCCESS_PATHS[1], start=1):
        conn.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?)", ["origin-job", index, state, T, None]
        )
    assert inspect().status == "verified_storage_evidence"


def test_single_batch_per_origin_job_required(support_db):
    conn, _, _, name, inspect = support_db
    table = name("bronze", "ingest_batches")
    conn.execute(f"INSERT INTO {table} SELECT * FROM {table}")
    conn.execute(
        f"UPDATE {table} SET batch_key='different' WHERE rowid=(SELECT max(rowid) FROM {table})"
    )
    assert inspect().status == "review_required"
