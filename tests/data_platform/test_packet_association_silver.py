"""Real DuckDB/audit persistence tests with association computation substituted."""

import hashlib
import json
from dataclasses import asdict, replace

import duckdb
import pytest

from nse_quant.data_platform import packet_association_silver as store
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.packet_reference_association import (
    ASSOCIATION_VERSION,
    PacketReferenceAssociation,
)

FRAME = "a" * 64
REFERENCE = "b" * 64


def result(status="blocked", reason="FRAME_BRONZE_RECEIPT_CONFLICT"):
    value = PacketReferenceAssociation(ASSOCIATION_VERSION, FRAME, 0, REFERENCE, status, reason)
    raw = json.dumps(asdict(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return replace(value, association_fingerprint=hashlib.sha256(raw.encode()).hexdigest())


@pytest.fixture
def setup(monkeypatch):
    inputs = [duckdb.connect(":memory:") for _ in range(3)]
    target = duckdb.connect(":memory:")
    state = {"result": result(), "calls": 0}

    def associate(*args, **kwargs):
        assert list(args) == inputs
        assert kwargs == {
            "frame_revision_id": FRAME,
            "packet_ordinal": 0,
            "reference_assessment_revision_id": REFERENCE,
        }
        state["calls"] += 1
        return state["result"]

    monkeypatch.setattr(store, "associate_packet_reference", associate)

    def run(**kwargs):
        options = {
            "frame_revision_id": FRAME,
            "packet_ordinal": 0,
            "reference_assessment_revision_id": REFERENCE,
            "actor_id": "test",
            "code_revision": "b378d92",
            "initialize": True,
        }
        options.update(kwargs)
        return store.persist_packet_association(*inputs, target, **options)

    yield inputs, target, state, run
    for connection in [*inputs, target]:
        connection.close()


def latest(target, job):
    return target.execute(
        "SELECT state FROM medallion_audit.job_events WHERE job_id=? "
        "ORDER BY event_index DESC LIMIT 1",
        [job],
    ).fetchone()[0]


def count(target, table):
    return target.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_persists_blocked_evidence_with_real_audit(setup):
    _, target, _, run = setup
    receipt = run()
    assert receipt["status"] == "blocked"
    assert receipt["inserted"] is True
    assert receipt["published"] is False
    assert latest(target, receipt["job_id"]) == "SUCCEEDED"
    row = target.execute(
        "SELECT result_json,published_at,effective_from,effective_to "
        "FROM silver.packet_reference_assessments"
    ).fetchone()
    assert json.loads(row[0])["reason_code"] == "FRAME_BRONZE_RECEIPT_CONFLICT"
    assert row[1:] == (None, None, None)
    assert count(target, "medallion_audit.dataset_contracts") == 1


def test_exact_retry_reuses_revision_but_appends_attempt(setup):
    _, target, state, run = setup
    first, second = run(), run(initialize=False)
    assert first["revision_id"] == second["revision_id"]
    assert first["job_id"] != second["job_id"]
    assert second["inserted"] is False
    assert count(target, "silver.packet_reference_assessments") == 1
    assert count(target, "silver.packet_reference_attempts") == 2
    assert state["calls"] == 2


def test_changed_blocked_evidence_preserves_and_links_prior(setup):
    _, target, state, run = setup
    first = run()
    state["result"] = result(reason="REFERENCE_ASSESSMENT_SUPERSEDED")
    second = run()
    assert first["revision_id"] != second["revision_id"]
    assert first["input_revision_id"] == second["input_revision_id"]
    links = target.execute(
        "SELECT supersedes_json FROM silver.packet_reference_assessments WHERE revision_id=?",
        [second["revision_id"]],
    ).fetchone()[0]
    assert json.loads(links) == [first["revision_id"]]
    assert count(target, "silver.packet_reference_assessments") == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("frame_revision_id", "A" * 64),
        ("packet_ordinal", True),
        ("packet_ordinal", 4096),
        ("actor_id", ""),
        ("code_revision", " "),
    ],
)
def test_invalid_request_before_initialization(setup, field, value):
    _, target, state, run = setup
    with pytest.raises(ValueError):
        run(**{field: value})
    assert state["calls"] == 0
    assert count(target, "information_schema.tables") == 0


def test_forbidden_target_rejected_without_audit_writes(setup):
    _, target, state, run = setup
    target.execute("CREATE TABLE option_stream (id INTEGER)")
    with pytest.raises(ValueError, match="DEDICATED_SILVER_REQUIRED"):
        run()
    assert state["calls"] == 0
    assert count(target, "information_schema.tables") == 1


def test_target_cannot_equal_input(setup):
    inputs, _, _, _ = setup
    with pytest.raises(ValueError, match="SEPARATE_ASSESSMENT_DATABASE_REQUIRED"):
        store.persist_packet_association(
            *inputs,
            inputs[0],
            frame_revision_id=FRAME,
            packet_ordinal=0,
            reference_assessment_revision_id=REFERENCE,
            actor_id="test",
            code_revision="head",
            initialize=True,
        )


def test_source_error_is_audited_failure_without_result(setup, monkeypatch):
    _, target, _, run = setup

    def fail(*args, **kwargs):
        raise RuntimeError("private exception text")

    monkeypatch.setattr(store, "associate_packet_reference", fail)
    with pytest.raises(RuntimeError):
        run()
    assert count(target, "silver.packet_reference_assessments") == 0
    states = target.execute(
        "SELECT state,reason_code FROM medallion_audit.job_events ORDER BY event_index"
    ).fetchall()
    assert states == [("PLANNED", None), ("RUNNING", None), ("FAILED", "EXECUTION_ERROR")]


def test_domain_insert_failure_rolls_back_and_audits(setup):
    _, target, state, run = setup
    first = run()
    target.execute(
        "ALTER TABLE silver.packet_reference_attempts ADD COLUMN required INTEGER DEFAULT 1"
    )
    state["result"] = result(reason="REFERENCE_OTHER_BLOCK")
    with pytest.raises(duckdb.Error):
        run()
    rows = target.execute("SELECT revision_id FROM silver.packet_reference_assessments").fetchall()
    assert rows == [(first["revision_id"],)]
    assert count(target, "silver.packet_reference_attempts") == 1
    assert target.execute(
        "SELECT count(*) FROM medallion_audit.job_events WHERE state='FAILED'"
    ).fetchone() == (1,)


@pytest.mark.parametrize(
    "field,value",
    [
        ("association_fingerprint", "bad"),
        ("frame_revision_id", "f" * 64),
        ("publication_asserted", True),
        ("decision_eligibility_asserted", True),
    ],
)
def test_bad_computation_result_not_committed(setup, field, value):
    _, target, state, run = setup
    state["result"] = replace(result(), **{field: value})
    with pytest.raises(ValueError, match="ASSOCIATION_RESULT_CONTRACT_MISMATCH"):
        run()
    assert count(target, "silver.packet_reference_assessments") == 0


def test_existing_revision_content_mismatch_fails(setup):
    _, target, _, run = setup
    run()
    target.execute("UPDATE silver.packet_reference_assessments SET result_json='{}'")
    with pytest.raises(ValueError, match="ASSOCIATION_VERSION_CONTENT_MISMATCH"):
        run()
    assert count(target, "silver.packet_reference_attempts") == 1


def test_schema_mismatch_fails_before_association(setup):
    _, target, state, run = setup
    run()
    target.execute("UPDATE silver.packet_reference_schema_versions SET version=999")
    with pytest.raises(ValueError, match="UNSUPPORTED_ASSOCIATION_STORE_SCHEMA"):
        run()
    assert state["calls"] == 1


def test_final_audit_failure_is_not_repaired_or_reported_success(setup, monkeypatch):
    _, target, _, run = setup
    original = AuditLedger.transition

    def transition(self, job_id, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("audit unavailable")
        return original(self, job_id, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", transition)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        run()
    assert count(target, "silver.packet_reference_assessments") == 1
    job = target.execute("SELECT job_id FROM silver.packet_reference_attempts").fetchone()[0]
    assert latest(target, job) == "RUNNING"
    monkeypatch.setattr(AuditLedger, "transition", original)
    retry = run()
    assert retry["inserted"] is False
    assert latest(target, retry["job_id"]) == "SUCCEEDED"
    assert latest(target, job) == "RUNNING"


def test_history_bound_is_not_quality_filtered(setup, monkeypatch):
    _, target, state, run = setup
    monkeypatch.setattr(store, "MAX_HISTORY", 0)
    run()
    state["result"] = result(reason="REFERENCE_NEW_BLOCK")
    with pytest.raises(ValueError, match="ASSOCIATION_HISTORY_LIMIT"):
        run()


def test_size_limit(setup, monkeypatch):
    _, target, _, run = setup
    monkeypatch.setattr(store, "MAX_RESULT_BYTES", 1)
    with pytest.raises(ValueError, match="ASSOCIATION_RESULT_LIMIT"):
        run()
    assert count(target, "silver.packet_reference_attempts") == 0


def test_same_file_target_alias_rejected(setup, tmp_path):
    inputs, _, _, _ = setup
    path = tmp_path / "shared.duckdb"
    first = duckdb.connect(str(path))
    second = duckdb.connect(str(path))
    try:
        with pytest.raises(ValueError, match="SEPARATE_ASSESSMENT_DATABASE_REQUIRED"):
            store.persist_packet_association(
                first,
                inputs[1],
                inputs[2],
                second,
                frame_revision_id=FRAME,
                packet_ordinal=0,
                reference_assessment_revision_id=REFERENCE,
                actor_id="test",
                code_revision="head",
                initialize=True,
            )
        assert count(first, "information_schema.tables") == 0
    finally:
        second.close()
        first.close()


def test_noninitializing_execution_does_not_create_schema(setup):
    _, target, state, run = setup
    with pytest.raises(duckdb.Error):
        run(initialize=False)
    assert count(target, "information_schema.tables") == 0
    assert state["calls"] == 0


def test_retry_detects_stored_status_tampering(setup):
    _, target, _, run = setup
    run()
    target.execute("UPDATE silver.packet_reference_assessments SET status='associated'")
    with pytest.raises(ValueError, match="ASSOCIATION_VERSION_CONTENT_MISMATCH"):
        run()
    assert count(target, "silver.packet_reference_attempts") == 1
