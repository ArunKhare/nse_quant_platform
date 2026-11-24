"""CLI boundary checks plus a small integration selection using committed fixtures."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import india_vix_replay_cli as cli

REVISION = "a" * 64


def valid_record() -> dict[str, Any]:
    return dict(
        quality_state="valid_observation",
        rejection_reason=None,
        observation=dict(
            iv30=0.185,
            value_percent=18.5,
            iv30_source="india_vix",
            mode="observation",
            session_calendar_verified=False,
            decision_eligibility_asserted=False,
        ),
        decision_eligibility_asserted=False,
    )


@pytest.fixture
def stores(tmp_path):
    paths = (tmp_path / "bronze.duckdb", tmp_path / "silver.duckdb")
    for path in paths:
        with duckdb.connect(str(path)) as conn:
            conn.execute("CREATE TABLE sentinel AS SELECT 1 AS value")
    return paths


def args(paths, revision=REVISION):
    return ["--bronze-db", str(paths[0]), "--silver-db", str(paths[1]), "--revision-id", revision]


def digest(paths):
    return [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]


def test_valid_report_readonly_and_unchanged_files(stores, monkeypatch, capsys):
    before = digest(stores)

    def replay(bronze, silver, *, revision_id):
        assert revision_id == REVISION
        for conn in (bronze, silver):
            assert conn.execute(
                "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
            ).fetchall() == [(True,)]
            with pytest.raises(duckdb.Error):
                conn.execute("CREATE TABLE forbidden(value INTEGER)")
        return valid_record()

    monkeypatch.setattr(cli, "_replay", replay)
    assert cli.main(args(stores)) == 0
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert output.err == ""
    assert report["status"] == "verified_valid_observation" and report["replay_verified"] is True
    assert report["decision_eligibility_asserted"] is False
    assert digest(stores) == before


def test_verified_rejection_is_not_successful_observation(stores, monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "_replay",
        lambda *a, **k: dict(
            quality_state="rejected",
            rejection_reason="future_or_stale_vix",
            observation=None,
            decision_eligibility_asserted=False,
        ),
    )
    assert cli.main(args(stores)) == 3
    report = json.loads(capsys.readouterr().out)
    assert report["replay_verified"] is True and report["status"] == "verified_rejected_evidence"
    assert report["observation"] is None


@pytest.mark.parametrize("problem", ["authority", "source", "quality", "nan", "exception", "reason"])
def test_fail_closed_without_leaking_details(stores, monkeypatch, capsys, problem):
    def replay(*a, **k):
        if problem == "exception":
            raise RuntimeError("TOP_SECRET_PROVIDER_PAYLOAD")
        record = valid_record()
        if problem == "authority":
            record["observation"]["decision_eligibility_asserted"] = True
        elif problem == "source":
            record["observation"]["iv30_source"] = "internal_cm"
        elif problem == "quality":
            record["quality_state"] = "unknown"
        elif problem == "nan":
            record["observation"]["iv30"] = float("nan")
        else:
            record = dict(
                quality_state="rejected",
                rejection_reason="TOP SECRET PAYLOAD",
                observation=None,
                decision_eligibility_asserted=False,
            )
        return record

    monkeypatch.setattr(cli, "_replay", replay)
    before = digest(stores)
    assert cli.main(args(stores)) == 2
    output = capsys.readouterr()
    assert output.out == "" and "SECRET" not in output.err
    report = json.loads(output.err)
    assert report["status"] == "verification_failed" and report["replay_verified"] is False
    assert digest(stores) == before


def test_missing_paths_do_not_create_files(tmp_path, capsys):
    paths = (tmp_path / "absent-b.duckdb", tmp_path / "absent-s.duckdb")
    assert cli.main(args(paths)) == 2
    assert all(not path.exists() for path in paths)
    assert json.loads(capsys.readouterr().err)["replay_verified"] is False


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_same_file_aliases_refused(stores, tmp_path, monkeypatch, capsys, alias):
    second = stores[0]
    if alias != "same":
        second = tmp_path / "alias.duckdb"
        if alias == "symlink":
            second.symlink_to(stores[0])
        else:
            second.hardlink_to(stores[0])

    calls = []

    def forbidden(*a, **k):
        calls.append(a)
        raise AssertionError("must reject before opening databases")

    monkeypatch.setattr(cli.duckdb, "connect", forbidden)
    assert cli.main(args((stores[0], second))) == 2
    assert calls == []
    assert json.loads(capsys.readouterr().err)["replay_verified"] is False


@pytest.mark.parametrize("revision", ["x" * 64, "A" * 64, "a" * 63, "a" * 65])
def test_revision_validation_happens_before_connect(stores, revision, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("must validate revision before connecting")

    monkeypatch.setattr(cli.duckdb, "connect", forbidden)
    with pytest.raises(SystemExit) as error:
        cli.main(args(stores, revision))
    assert error.value.code == 2


def test_first_handle_closed_if_second_open_fails(stores, monkeypatch, capsys):
    real_connect = duckdb.connect
    handles: list[duckdb.DuckDBPyConnection] = []

    def connect(path, *, read_only):
        assert read_only is True
        if handles:
            raise RuntimeError("SECRET_OPEN_FAILURE")
        conn = real_connect(path, read_only=read_only)
        handles.append(conn)
        return conn

    monkeypatch.setattr(cli.duckdb, "connect", connect)
    assert cli.main(args(stores)) == 2
    assert "SECRET" not in capsys.readouterr().err
    with pytest.raises(duckdb.Error):
        handles[0].execute("SELECT 1")


def test_corrupt_database_not_modified(tmp_path, capsys):
    paths = (tmp_path / "broken-b.duckdb", tmp_path / "broken-s.duckdb")
    for path in paths:
        path.write_bytes(b"not a DuckDB database")
    before = digest(paths)
    assert cli.main(args(paths)) == 2
    assert digest(paths) == before
    assert json.loads(capsys.readouterr().err)["replay_verified"] is False


@pytest.mark.parametrize("case", ["valid", "rejected", "tampered"])
def test_committed_recording_integration(tmp_path, capsys, case):
    import test_india_vix_recording as fixture

    bp, sp = tmp_path / "bronze.duckdb", tmp_path / "silver.duckdb"
    capture = fixture.capture(-1) if case == "rejected" else fixture.capture()
    pins = fixture.preserve(bp, capture)["pins"]
    revision = fixture.promote(bp, sp, pins)["revision_id"]
    if case == "tampered":
        with duckdb.connect(str(sp)) as conn:
            table = fixture.m.table(conn, fixture.m.RECORDS)
            conn.execute(f"UPDATE {table} SET record_bytes=encode('{{}}')")
    before = digest((bp, sp))
    code = cli.main(args((bp, sp), revision))
    assert code == {"valid": 0, "rejected": 3, "tampered": 2}[case]
    output = capsys.readouterr()
    report = json.loads(output.err if code == 2 else output.out)
    assert report["replay_verified"] is (case != "tampered")
    assert digest((bp, sp)) == before


def test_report_drops_unknown_raw_fields(stores, monkeypatch, capsys):
    record = valid_record()
    record["observation"]["raw_payload_json"] = "SECRET_RAW_PAYLOAD"
    monkeypatch.setattr(cli, "_replay", lambda *a, **k: record)
    assert cli.main(args(stores)) == 0
    output = capsys.readouterr()
    assert "SECRET" not in output.out and "raw_payload_json" not in output.out
