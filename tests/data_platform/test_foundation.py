"""Foundation tests use real disposable DuckDB connections."""

from dataclasses import replace

import duckdb
import pytest

from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy


def contract():
    return DatasetContract(
        name="bronze.option_events",
        version="1",
        layer=Layer.BRONZE,
        write_policy=WritePolicy.APPEND_OBSERVATIONS,
        entity_keys=("capture_event_id",),
        required_columns=("capture_event_id", "received_at", "source", "payload_hash"),
        owner="capture",
    )


@pytest.fixture
def ledger():
    conn = duckdb.connect(":memory:")
    result = AuditLedger(conn)
    result.initialize()
    try:
        yield result
    finally:
        conn.close()


def plan(ledger, **extra):
    return ledger.plan_job(
        command_name="test.build",
        actor_id="test",
        scope_ref="scope-1",
        code_revision="commit-1",
        config_hash="hash-1",
        **extra,
    )


def states(ledger, job):
    return [
        row[0]
        for row in ledger.conn.execute(
            "SELECT state FROM medallion_audit.job_events WHERE job_id = ? ORDER BY event_index",
            [job],
        ).fetchall()
    ]


def test_import_and_constructor_do_not_initialize():
    conn = duckdb.connect(":memory:")
    try:
        AuditLedger(conn)
        assert conn.execute("SHOW TABLES").fetchall() == []
        assert (
            conn.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = 'medallion_audit'"
            ).fetchall()
            == []
        )
    finally:
        conn.close()


def test_initialize_is_repeatable_and_preserves_domain_data(ledger):
    ledger.conn.execute("CREATE TABLE original_data AS SELECT 42 AS value")
    ledger.initialize()
    assert ledger.conn.execute("SELECT * FROM original_data").fetchall() == [(42,)]
    assert (
        ledger.conn.execute("SELECT count(*) FROM medallion_audit.schema_versions").fetchone()[0]
        == 1
    )


def test_contract_retry_and_conflict(ledger):
    value = contract()
    assert ledger.register_contract(value)
    assert not ledger.register_contract(value)
    with pytest.raises(ValueError, match="version increment"):
        ledger.register_contract(replace(value, owner="different"))
    assert ledger.register_contract(replace(value, version="2"))


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "gold.option_events"},
        {"write_policy": WritePolicy.VERSIONED_BUILDS},
        {"owner": ""},
        {"required_columns": ("capture_event_id",)},
        {"entity_keys": ("missing",)},
        {"entity_keys": ("capture_event_id", "capture_event_id")},
    ],
)
def test_invalid_contracts(changes):
    with pytest.raises(ValueError):
        replace(contract(), **changes)


def test_success_events_are_appended(ledger):
    job = plan(ledger)
    with ledger.execution(job):
        pass
    assert states(ledger, job) == ["PLANNED", "RUNNING", "SUCCEEDED"]
    with pytest.raises(ValueError, match="Invalid transition"):
        ledger.transition(job, JobState.RUNNING)
    assert len(states(ledger, job)) == 3


def test_failure_does_not_persist_exception_secrets(ledger):
    job = plan(ledger)
    with pytest.raises(RuntimeError, match="secret"), ledger.execution(job):
        raise RuntimeError("secret-token-do-not-log")
    assert states(ledger, job) == ["PLANNED", "RUNNING", "FAILED"]
    reasons = ledger.conn.execute(
        "SELECT reason_code FROM medallion_audit.job_events WHERE job_id = ?",
        [job],
    ).fetchall()
    assert reasons[-1] == ("EXECUTION_ERROR",)


def test_cancelled_execution(ledger):
    job = plan(ledger)
    with pytest.raises(KeyboardInterrupt), ledger.execution(job):
        raise KeyboardInterrupt()
    assert states(ledger, job)[-1] == "CANCELLED"


def test_publication_lifecycle(ledger):
    job = plan(ledger)
    for state in (
        JobState.RUNNING,
        JobState.STAGED,
        JobState.VALIDATED,
        JobState.PUBLISHED,
        JobState.SUCCEEDED,
    ):
        ledger.transition(job, state)
    assert states(ledger, job) == [
        "PLANNED",
        "RUNNING",
        "STAGED",
        "VALIDATED",
        "PUBLISHED",
        "SUCCEEDED",
    ]


def test_parent_and_unknown_job(ledger):
    parent = plan(ledger)
    child = plan(ledger, parent_job_id=parent)
    assert (
        ledger.conn.execute(
            "SELECT parent_job_id FROM medallion_audit.jobs WHERE job_id = ?",
            [child],
        ).fetchone()[0]
        == parent
    )
    with pytest.raises(ValueError, match="Parent"):
        plan(ledger, parent_job_id="missing")
    with pytest.raises(ValueError, match="Unknown"):
        ledger.transition("missing", JobState.RUNNING)
    assert ledger.conn.execute("SELECT count(*) FROM medallion_audit.jobs").fetchone()[0] == 2


def test_reason_code_validation(ledger):
    job = plan(ledger)
    with pytest.raises(ValueError, match="Reason"):
        ledger.transition(job, JobState.FAILED, "token=secret")
    assert states(ledger, job) == ["PLANNED"]


def test_unknown_schema_version_fails_closed(ledger):
    ledger.conn.execute("UPDATE medallion_audit.schema_versions SET version = 99")
    with pytest.raises(ValueError, match="Unsupported"):
        ledger.initialize()


def test_audit_failure_keeps_original_exception(ledger, monkeypatch):
    job = plan(ledger)
    original = ledger.transition

    def fail_recording(job_id, state, reason_code=None):
        if state == JobState.FAILED:
            raise RuntimeError("audit unavailable")
        original(job_id, state, reason_code)

    monkeypatch.setattr(ledger, "transition", fail_recording)
    with pytest.raises(ValueError, match="domain failure") as error, ledger.execution(job):
        raise ValueError("domain failure")
    assert "Audit failure: RuntimeError" in error.value.__notes__


def load_inspector():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "inspect_medallion_audit",
        root / "scripts/inspect/inspect_medallion_audit.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inspector_does_not_create_missing_database(tmp_path):
    module = load_inspector()
    missing = tmp_path / "missing.duckdb"
    with pytest.raises(SystemExit) as error:
        module.main(["--db", str(missing)])
    assert error.value.code == 2
    assert not missing.exists()


def test_inspector_reads_committed_audit_without_mutation(tmp_path, capsys):
    module = load_inspector()
    path = tmp_path / "audit.duckdb"
    conn = duckdb.connect(str(path))
    ledger = AuditLedger(conn)
    ledger.initialize()
    job = plan(ledger)
    with ledger.execution(job):
        pass
    conn.close()
    assert module.main(["--db", str(path), "--job-id", job]) == 0
    assert "SUCCEEDED" in capsys.readouterr().out
    conn = duckdb.connect(str(path), read_only=True)
    try:
        row = conn.execute("SELECT count(*) FROM medallion_audit.job_events").fetchone()
        assert row is not None
        assert row[0] == 3
    finally:
        conn.close()
