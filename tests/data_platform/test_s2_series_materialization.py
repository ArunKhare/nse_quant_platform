"""Actual temporary DuckDB and audited EOD replay; no operational stores."""

import builtins
import hashlib
import json

import duckdb
import pytest

from nse_quant.analytics import s2_iv30_history as history
from nse_quant.data_platform import s2_series_cli as cli
from nse_quant.data_platform import s2_series_materialization as api
from nse_quant.data_platform.audit import AuditLedger

REVISION = "a" * 40
OBSERVATION = "b" * 64


def artifact(value=15):
    raw = f"day,close\n2026-11-20,{value}\n2026-11-23,16\n".encode()
    built = history.build_history(
        raw_csv=raw,
        expected_raw_sha256=api.sha(raw),
        source_reference="synthetic-eod",
        received_at="2026-11-24T00:00:00+00:00",
        as_of="2026-11-25T00:00:00+00:00",
        date_column="day",
        close_column="close",
    )
    return api.prepare_eod(built)


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "materializations.duckdb"
    with duckdb.connect(str(path)) as conn:
        api.initialize(conn, actor_id="fixture", code_revision=REVISION)
    return path


def persist(path, raw):
    with duckdb.connect(str(path)) as writer:
        return api.persist(
            writer,
            raw=raw,
            observation_id=OBSERVATION,
            expected_sha256=api.sha(raw),
            actor_id="fixture",
            code_revision=REVISION,
        )


def replay(path, raw):
    with duckdb.connect(str(path), read_only=True) as reader:
        return api.replay(reader, kind=api.EOD, observation_id=OBSERVATION, expected_sha256=api.sha(raw))


def test_actual_duckdb_eod_round_trip_and_exact_retry(store):
    raw = artifact()
    first = persist(store, raw)
    second = persist(store, raw)
    assert not first["exact_retry"] and second["exact_retry"]
    assert first["revision_id"] == second["revision_id"]
    assert replay(store, raw) == raw
    assert json.loads(raw)["content"]["rows"][0]["iv30"] == 0.15
    with duckdb.connect(str(store), read_only=True) as conn:
        assert conn.execute("SELECT count(*) FROM medallion_audit.jobs").fetchone() == (1,)


def test_conflict_retained_blocks_both_pins(store):
    first, second = artifact(), artifact(17)
    persist(store, first)
    assert persist(store, second)["conflicted"]
    assert persist(store, first)["conflicted"]
    for raw in (first, second):
        with pytest.raises(ValueError, match="CONFLICTED"):
            replay(store, raw)
    with duckdb.connect(str(store), read_only=True) as conn:
        assert conn.execute("SELECT count(*) FROM silver.s2_series_materializations").fetchone() == (2,)


def test_unreviewed_digest_has_no_write(store):
    with duckdb.connect(str(store)) as conn:
        with pytest.raises(ValueError, match="REVIEWED"):
            api.persist(
                conn,
                raw=artifact(),
                observation_id=OBSERVATION,
                expected_sha256="0" * 64,
                actor_id="fixture",
                code_revision=REVISION,
            )
        assert conn.execute("SELECT count(*) FROM medallion_audit.jobs").fetchone() == (0,)


@pytest.mark.parametrize(
    "field,value",
    [
        ("publication_asserted", True),
        ("decision_eligibility_asserted", True),
        ("iv30_source", "internal_cm"),
        ("atomic_cross_database_snapshot_asserted", True),
    ],
)
def test_authority_and_source_changes_rejected_even_with_new_hash(store, field, value):
    doc = json.loads(artifact())
    doc[field] = value
    with pytest.raises(ValueError, match="RECOMPUTE"):
        persist(store, api.canonical(doc))


def test_rehashed_eod_output_must_recompute(store):
    doc = json.loads(artifact())
    doc["content"]["rows"][0]["iv30"] = 42
    with pytest.raises(ValueError, match="REPLAY_MISMATCH"):
        persist(store, api.canonical(doc))


def test_interrupted_original_job_blocks_without_healing(store):
    raw = artifact()
    with duckdb.connect(str(store)) as conn:
        AuditLedger(conn).plan_job(
            command_name=api.COMMAND,
            actor_id="fixture",
            code_revision=REVISION,
            scope_ref=api._scope(api.EOD, OBSERVATION),
            config_hash=api.sha(raw),
        )
    with pytest.raises(ValueError, match="ORPHAN_OR_INTERRUPTED"):
        persist(store, raw)


def test_transaction_rollback_keeps_failed_audit_obligation(store, monkeypatch):
    original = api._insert

    def fail_after_insert(*args):
        original(*args)
        raise RuntimeError("injected insert failure")

    monkeypatch.setattr(api, "_insert", fail_after_insert)
    with pytest.raises(RuntimeError, match="injected"):
        persist(store, artifact())
    with duckdb.connect(str(store), read_only=True) as conn:
        assert conn.execute("SELECT count(*) FROM silver.s2_series_materializations").fetchone() == (0,)
        assert conn.execute("SELECT state FROM medallion_audit.job_events ORDER BY event_index").fetchall() == [
            ("PLANNED",),
            ("RUNNING",),
            ("FAILED",),
        ]
    with pytest.raises(ValueError, match="ORPHAN_OR_INTERRUPTED"):
        persist(store, artifact())


@pytest.mark.parametrize(
    "problem",
    [
        "body",
        "final_audit",
        "extra_table",
        "extra_column",
        "definition",
        "contract",
        "orphan_event",
    ],
)
def test_integrity_and_schema_fail_closed(store, problem):
    raw = artifact()
    persist(store, raw)
    sql = {
        "body": "UPDATE silver.s2_series_materializations SET body='bad'::BLOB",
        "final_audit": "DELETE FROM medallion_audit.job_events WHERE state='SUCCEEDED'",
        "extra_table": "CREATE TABLE unexpected(x INTEGER)",
        "extra_column": "ALTER TABLE silver.s2_series_materializations ADD COLUMN unexpected INTEGER",
        "definition": "UPDATE silver.s2_series_materialization_definition SET definition='bad'::BLOB",
        "contract": "UPDATE medallion_audit.dataset_contracts SET fingerprint='bad'",
        "orphan_event": "INSERT INTO medallion_audit.job_events VALUES ('orphan',1,'PLANNED',current_timestamp,NULL)",
    }[problem]
    with duckdb.connect(str(store)) as conn:
        conn.execute(sql)
    with pytest.raises(ValueError):
        replay(store, raw)


def test_replay_requires_independent_readonly_handle(store):
    raw = artifact()
    persist(store, raw)
    with duckdb.connect(str(store)) as writer:
        with pytest.raises(ValueError, match="READONLY"):
            api.replay(writer, kind=api.EOD, observation_id=OBSERVATION, expected_sha256=api.sha(raw))
        cursor = writer.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                api.persist(
                    writer,
                    raw=raw,
                    observation_id=OBSERVATION,
                    expected_sha256=api.sha(raw),
                    actor_id="fixture",
                    code_revision=REVISION,
                    bronze=cursor,
                )
        finally:
            cursor.close()


def test_replay_changes_no_file_bytes(store):
    raw = artifact()
    persist(store, raw)
    before = hashlib.sha256(store.read_bytes()).hexdigest()
    replay(store, raw)
    assert hashlib.sha256(store.read_bytes()).hexdigest() == before


def test_initialization_does_not_adopt_existing_store(store):
    with duckdb.connect(str(store)) as writer, pytest.raises(ValueError, match="EMPTY_DEDICATED"):
        api.initialize(writer, actor_id="fixture", code_revision=REVISION)
    with duckdb.connect(":memory:") as memory, pytest.raises(ValueError, match="FILE_BACKED"):
        api.initialize(memory, actor_id="fixture", code_revision=REVISION)


def test_cli_default_does_no_io(tmp_path, monkeypatch, capsys):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "duckdb" or name == "nse_quant.data_platform":
            raise AssertionError("Planning imported execution dependencies")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert (
        cli.main(["init", "--db", str(tmp_path / "missing.duckdb"), "--actor", "fixture", "--code-revision", REVISION])
        == 0
    )
    assert list(tmp_path.iterdir()) == []
    assert "PLANNED_NO_IO" in capsys.readouterr().out


def test_cli_eod_prepare_persist_and_replay(tmp_path, capsys):
    source, prepared, replayed = (tmp_path / name for name in ("input.csv", "prepared.json", "replayed.json"))
    source.write_bytes(b"day,close\n2026-11-20,15\n")
    path = tmp_path / "cli_materializations.duckdb"
    assert (
        cli.main(
            [
                "prepare-eod",
                "--csv",
                str(source),
                "--expected-csv-sha256",
                api.sha(source.read_bytes()),
                "--source-reference",
                "synthetic-eod",
                "--received-at",
                "2026-11-24T00:00:00+00:00",
                "--as-of",
                "2026-11-25T00:00:00+00:00",
                "--date-column",
                "day",
                "--close-column",
                "close",
                "--output",
                str(prepared),
                "--execute",
            ]
        )
        == 0
    )
    assert cli.main(["init", "--db", str(path), "--actor", "fixture", "--code-revision", REVISION, "--execute"]) == 0
    digest = api.sha(prepared.read_bytes())
    common = ["--db", str(path), "--observation-id", OBSERVATION, "--expected-sha256", digest, "--execute"]
    assert (
        cli.main(
            [
                "persist",
                *common,
                "--artifact",
                str(prepared),
                "--actor",
                "fixture",
                "--code-revision",
                REVISION,
            ]
        )
        == 0
    )
    assert cli.main(["replay", *common, "--kind", api.EOD, "--output", str(replayed)]) == 0
    assert prepared.read_bytes() == replayed.read_bytes()
    with pytest.raises(FileExistsError):
        cli.main(["replay", *common, "--kind", api.EOD, "--output", str(replayed)])
    capsys.readouterr()


def test_unknown_kind_rejected_before_audit(store):
    doc = json.loads(artifact())
    doc["kind"] = "gold"
    with pytest.raises(ValueError, match="UNSUPPORTED"):
        persist(store, api.canonical(doc))


def test_minute_envelope_requires_native_sources(store):
    raw = api._wrap(api.MINUTE, dict(revisions=["c" * 64]))
    with pytest.raises(ValueError, match="NATIVE_MINUTE_REPLAY_SOURCES"):
        persist(store, raw)
