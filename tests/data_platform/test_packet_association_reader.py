"""Real DuckDB snapshot/graph/audit checks; current association boundary substituted."""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import packet_association_reader as reader
from nse_quant.data_platform.packet_association_silver import COMMAND, STORE_VERSION
from nse_quant.data_platform.packet_reference_association import (
    ASSOCIATION_VERSION,
    PacketReferenceAssociation,
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@pytest.fixture
def setup(monkeypatch):
    inputs = [duckdb.connect(":memory:") for _ in range(3)]
    db = duckdb.connect(":memory:")
    db.execute("CREATE SCHEMA silver")
    db.execute("CREATE SCHEMA medallion_audit")
    db.execute("CREATE TABLE silver.packet_reference_schema_versions AS SELECT 1 AS version")
    db.execute("CREATE TABLE medallion_audit.schema_versions AS SELECT 1 AS version")
    db.execute(
        "CREATE TABLE silver.packet_reference_assessments (revision_id VARCHAR,"
        "input_revision_id VARCHAR,source_observation_id VARCHAR,packet_ordinal INTEGER,"
        "reference_assessment_revision_id VARCHAR,store_version VARCHAR,"
        "association_version VARCHAR,status VARCHAR,reason_code VARCHAR,"
        "association_fingerprint VARCHAR,result_json VARCHAR,supersedes_json VARCHAR,"
        "recorded_at TIMESTAMPTZ,published_at TIMESTAMPTZ,effective_from TIMESTAMPTZ,"
        "effective_to TIMESTAMPTZ,first_job_id VARCHAR)"
    )
    db.execute("CREATE TABLE silver.packet_reference_attempts (job_id VARCHAR,revision_id VARCHAR)")
    db.execute(
        "CREATE TABLE medallion_audit.jobs (job_id VARCHAR,command_name VARCHAR,"
        "scope_ref VARCHAR,config_hash VARCHAR)"
    )
    db.execute(
        "CREATE TABLE medallion_audit.job_events (job_id VARCHAR,event_index INTEGER,state VARCHAR)"
    )
    db.execute(
        "CREATE TABLE medallion_audit.dataset_contracts (dataset_name VARCHAR,"
        "contract_version VARCHAR,fingerprint VARCHAR,contract_json VARCHAR)"
    )
    contract = {
        "name": "silver.packet_reference_assessments",
        "version": "1",
        "layer": "silver",
        "write_policy": "append_revisions",
        "entity_keys": ["revision_id"],
        "required_columns": ["revision_id", "source_observation_id", "recorded_at"],
        "owner": "native_packet_reference",
    }
    db.execute(
        "INSERT INTO medallion_audit.dataset_contracts VALUES (?,?,?,?)",
        [contract["name"], "1", digest(contract), canonical(contract)],
    )
    result = PacketReferenceAssociation(
        ASSOCIATION_VERSION, "a" * 64, 0, "b" * 64, "blocked", "REFERENCE_ASSESSMENT_SUPERSEDED"
    )
    result = replace(result, association_fingerprint=digest(asdict(result)))
    versions = [STORE_VERSION, ASSOCIATION_VERSION]
    group = digest(["a" * 64, 0, "b" * 64, versions])
    revision = digest([group, result.association_fingerprint])
    db.execute(
        "INSERT INTO silver.packet_reference_assessments VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            revision,
            group,
            "a" * 64,
            0,
            "b" * 64,
            *versions,
            result.status,
            result.reason_code,
            result.association_fingerprint,
            canonical(asdict(result)),
            "[]",
            datetime.now(UTC),
            None,
            None,
            None,
            "job1",
        ],
    )
    db.execute("INSERT INTO silver.packet_reference_attempts VALUES (?,?)", ["job1", revision])
    db.execute(
        "INSERT INTO medallion_audit.jobs VALUES (?,?,?,?)",
        ["job1", COMMAND, "sha256:" + group, digest(versions)],
    )
    db.execute("INSERT INTO medallion_audit.job_events VALUES ('job1',1,'SUCCEEDED')")
    state = {"result": result, "calls": 0}

    def associate(*args, **kwargs):
        assert list(args) == inputs
        assert kwargs == {
            "frame_revision_id": "a" * 64,
            "packet_ordinal": 0,
            "reference_assessment_revision_id": "b" * 64,
        }
        state["calls"] += 1
        return state["result"]

    monkeypatch.setattr(reader, "associate_packet_reference", associate)

    def run(pin=revision):
        return reader.read_packet_assessment(*inputs, db, assessment_revision_id=pin)

    yield db, state, run, revision, group
    for connection in [*inputs, db]:
        connection.close()


def test_verified_current_preserves_blocked_domain_result(setup):
    _, state, run, _, _ = setup
    evidence = run()
    assert evidence.status == "verified_current"
    assert evidence.association == state["result"]
    assert evidence.association.status == "blocked"
    assert evidence.successful_attempt_job_ids == ("job1",)
    assert not evidence.publication_asserted
    assert not evidence.historical_validity_asserted
    assert not evidence.decision_eligibility_asserted
    assert run() == evidence
    assert state["calls"] == 2


@pytest.mark.parametrize(
    "sql,reason",
    [
        (
            "UPDATE silver.packet_reference_schema_versions SET version=2",
            "UNSUPPORTED_ASSESSMENT_SCHEMA",
        ),
        ("DELETE FROM medallion_audit.dataset_contracts", "ASSESSMENT_CONTRACT_NOT_VERIFIED"),
        (
            "UPDATE silver.packet_reference_assessments SET store_version='bad'",
            "UNSUPPORTED_ASSESSMENT_VERSION",
        ),
        (
            "UPDATE silver.packet_reference_assessments SET packet_ordinal=-1",
            "INVALID_ASSESSMENT_SOURCE_PINS",
        ),
        (
            "UPDATE silver.packet_reference_assessments SET source_observation_id=repeat('e',64)",
            "ASSESSMENT_IDENTITY_MISMATCH",
        ),
        (
            "UPDATE silver.packet_reference_assessments SET published_at=now()",
            "UNSUPPORTED_TEMPORAL_CLAIMS",
        ),
        ("DELETE FROM silver.packet_reference_attempts", "ASSESSMENT_ATTEMPT_LINEAGE_MISSING"),
        ("DELETE FROM medallion_audit.jobs", "ASSESSMENT_ATTEMPT_AUDIT_MISMATCH"),
        ("UPDATE medallion_audit.jobs SET scope_ref='bad'", "ASSESSMENT_ATTEMPT_AUDIT_MISMATCH"),
        (
            "UPDATE medallion_audit.job_events SET state='RUNNING'",
            "ASSESSMENT_ATTEMPT_NOT_TERMINAL",
        ),
        ("DELETE FROM medallion_audit.job_events", "ASSESSMENT_ATTEMPT_NOT_TERMINAL"),
        (
            "UPDATE medallion_audit.job_events SET state='FAILED'",
            "ASSESSMENT_NO_SUCCESSFUL_ATTEMPT",
        ),
        (
            "UPDATE silver.packet_reference_assessments SET result_json='{}'",
            "MALFORMED_ASSESSMENT_RESULT",
        ),
        (
            "UPDATE silver.packet_reference_assessments SET result_json='not-json'",
            "MALFORMED_ASSESSMENT_RESULT",
        ),
        (
            "UPDATE silver.packet_reference_assessments SET result_json=repeat('x',1048577)",
            "ASSESSMENT_RESULT_LIMIT",
        ),
        (
            "UPDATE silver.packet_reference_assessments SET status='associated'",
            "ASSESSMENT_RESULT_IDENTITY_MISMATCH",
        ),
        (
            "UPDATE silver.packet_reference_assessments SET supersedes_json='null'",
            "INVALID_SUPERSESSION_EVIDENCE",
        ),
        (
            "UPDATE silver.packet_reference_assessments SET supersedes_json='[true]'",
            "INVALID_SUPERSESSION_LINK",
        ),
    ],
)
def test_tampering_and_missing_audit_block_before_source(setup, sql, reason):
    db, state, run, _, _ = setup
    db.execute(sql)
    assert run().reason_code == reason
    assert state["calls"] == 0


def test_new_failed_unsupported_blocked_assessment_still_invalidates(setup):
    db, state, run, revision, _ = setup
    db.execute(
        "INSERT INTO silver.packet_reference_assessments SELECT repeat('f',64),"
        "input_revision_id,source_observation_id,packet_ordinal,"
        "reference_assessment_revision_id,'unsupported',association_version,'blocked',"
        "reason_code,association_fingerprint,result_json,?,recorded_at,"
        "published_at,effective_from,effective_to,'failed-job' "
        "FROM silver.packet_reference_assessments",
        [canonical([revision])],
    )
    assert run().reason_code == "ASSESSMENT_SUPERSEDED"
    assert state["calls"] == 0


def test_unlinked_graph_heads_are_ambiguous_not_latest_wins(setup):
    db, state, run, _, _ = setup
    db.execute(
        "INSERT INTO silver.packet_reference_assessments SELECT repeat('f',64),"
        "input_revision_id,source_observation_id,packet_ordinal,"
        "reference_assessment_revision_id,store_version,association_version,status,"
        "reason_code,association_fingerprint,result_json,'[]',recorded_at,"
        "published_at,effective_from,effective_to,first_job_id "
        "FROM silver.packet_reference_assessments"
    )
    assert run().reason_code == "AMBIGUOUS_ACTIVE_ASSESSMENTS"
    assert state["calls"] == 0


@pytest.mark.parametrize("kind", ["self", "dangling"])
def test_graph_errors(setup, kind):
    db, _, run, revision, _ = setup
    link = revision if kind == "self" else "f" * 64
    db.execute(
        "UPDATE silver.packet_reference_assessments SET supersedes_json=?", [canonical([link])]
    )
    expected = "SUPERSESSION_CYCLE" if kind == "self" else "DANGLING_SUPERSESSION_LINK"
    assert run().reason_code == expected


def test_fresh_source_change_blocks_without_writing(setup):
    db, state, run, _, _ = setup
    state["result"] = replace(state["result"], reason_code="FRAME_BRONZE_RECEIPT_CONFLICT")
    before = db.execute("SELECT result_json FROM silver.packet_reference_assessments").fetchall()
    assert run().reason_code == "CURRENT_ASSOCIATION_EVIDENCE_CHANGED"
    after = db.execute("SELECT result_json FROM silver.packet_reference_assessments").fetchall()
    assert after == before


def test_pending_retry_blocks_even_with_successful_first_attempt(setup):
    db, _, run, revision, _ = setup
    db.execute("INSERT INTO silver.packet_reference_attempts VALUES ('job2',?)", [revision])
    db.execute(
        "INSERT INTO medallion_audit.jobs SELECT 'job2',command_name,scope_ref,config_hash "
        "FROM medallion_audit.jobs"
    )
    db.execute("INSERT INTO medallion_audit.job_events VALUES ('job2',1,'RUNNING')")
    assert run().reason_code == "ASSESSMENT_ATTEMPT_NOT_TERMINAL"
    db.execute("INSERT INTO medallion_audit.job_events VALUES ('job2',2,'FAILED')")
    assert run().status == "verified_current"


@pytest.mark.parametrize("pin", ["", "A" * 64, "a" * 63])
def test_bad_pin(setup, pin):
    _, state, run, _, _ = setup
    with pytest.raises(ValueError):
        run(pin)
    assert state["calls"] == 0


def test_limits_and_missing_pin(setup, monkeypatch):
    _, _, run, _, _ = setup
    assert run("f" * 64).reason_code == "ASSESSMENT_NOT_FOUND"
    monkeypatch.setattr(reader, "MAX_ATTEMPTS", 0)
    assert run().reason_code == "ASSESSMENT_ATTEMPT_LIMIT"
    monkeypatch.setattr(reader, "MAX_ASSESSMENTS", 0)
    assert run().reason_code == "ASSESSMENT_HISTORY_LIMIT"


def test_duplicate_graph_links_block(setup):
    db, _, run, revision, _ = setup
    db.execute(
        "UPDATE silver.packet_reference_assessments SET supersedes_json=?",
        [canonical([revision, revision])],
    )
    assert run().reason_code == "DUPLICATE_SUPERSESSION_LINK"


def test_oversized_graph_links_block(setup):
    db, _, run, _, _ = setup
    db.execute("UPDATE silver.packet_reference_assessments SET supersedes_json=repeat('x',100001)")
    assert run().reason_code == "INVALID_SUPERSESSION_EVIDENCE"


def test_source_execution_error_propagates(setup, monkeypatch):
    _, _, run, _, _ = setup

    def fail(*args, **kwargs):
        raise RuntimeError("source unavailable")

    monkeypatch.setattr(reader, "associate_packet_reference", fail)
    with pytest.raises(RuntimeError, match="source unavailable"):
        run()


def test_real_readonly_assessment_file_is_unchanged(setup, tmp_path, monkeypatch):
    db, state, _, revision, _ = setup
    path = tmp_path / "assessments.quoted'name.duckdb"
    escaped = str(path).replace("'", "''")
    db.execute(f"ATTACH '{escaped}' AS export_target")
    db.execute("COPY FROM DATABASE memory TO export_target")
    db.execute("DETACH export_target")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    sources = [duckdb.connect(":memory:") for _ in range(3)]
    monkeypatch.setattr(reader, "associate_packet_reference", lambda *a, **kw: state["result"])
    assessment = duckdb.connect(str(path), read_only=True)
    try:
        result = reader.read_packet_assessment(
            *sources, assessment, assessment_revision_id=revision
        )
        assert result.status == "verified_current"
    finally:
        assessment.close()
        for connection in sources:
            connection.close()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_input_cannot_be_assessment_connection(setup):
    db, _, _, revision, _ = setup
    with pytest.raises(ValueError, match="SEPARATE_ASSESSMENT_DATABASE_REQUIRED"):
        reader.read_packet_assessment(db, db, db, db, assessment_revision_id=revision)
