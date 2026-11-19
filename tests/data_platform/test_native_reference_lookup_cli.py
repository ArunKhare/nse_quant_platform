"""Operational boundary tests; reader integrity tests remain authoritative."""

from __future__ import annotations

import builtins
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from nse_quant.data_platform.native_reference_lookup_cli import main

PIN = "a" * 64


def arguments(tmp_path: Path) -> list[str]:
    return [
        "--bronze-db",
        str(tmp_path / "bronze.duckdb"),
        "--silver-db",
        str(tmp_path / "silver.duckdb"),
        "--assessment-revision-id",
        PIN,
        "--instrument-token",
        "123",
    ]


def test_plan_does_not_import_database_or_reader(tmp_path, monkeypatch, capsys):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"duckdb", "nse_quant.data_platform.native_reference_reader"}:
            raise AssertionError("Plan imported execution dependency")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert main(arguments(tmp_path)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PLANNED"
    assert result["inputs_verified"] is False
    assert result["publication_asserted"] is False
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("token", ["0", "-1", "4294967296", "abc"])
def test_invalid_token(tmp_path, token):
    args = arguments(tmp_path)
    args[-1] = token
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2


@pytest.mark.parametrize("pin", ["A" * 64, "a" * 63, "../bad"])
def test_invalid_pin(tmp_path, pin):
    args = arguments(tmp_path)
    args[-3] = pin
    with pytest.raises(SystemExit):
        main(args)


def test_missing_execution_inputs_do_not_create_files(tmp_path):
    with pytest.raises(SystemExit):
        main(arguments(tmp_path) + ["--execute"])
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "status,expected",
    [
        ("matched", 0),
        ("ambiguous", 2),
        ("unresolved", 2),
        ("blocked", 2),
    ],
)
def test_read_only_connections_and_exact_result(tmp_path, monkeypatch, capsys, status, expected):
    for name in ("bronze.duckdb", "silver.duckdb"):
        (tmp_path / name).touch()
    opened = []
    closed = []

    class Connection:
        def __init__(self, path):
            self.path = path

        def close(self):
            closed.append(self.path)

    def connect(path, *, read_only):
        assert read_only is True
        opened.append(path)
        return Connection(path)

    @dataclass
    class Result:
        status: str
        reason_code: str = "EXACT_READER_REASON"
        canonical_contract_id: None = None
        historical_validity_asserted: bool = False
        publication_asserted: bool = False

    def lookup(bronze, silver, *, assessment_revision_id, instrument_token):
        assert bronze.path != silver.path
        assert assessment_revision_id == PIN
        assert instrument_token == 123
        return Result(status)

    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=connect))
    monkeypatch.setitem(
        sys.modules,
        "nse_quant.data_platform.native_reference_reader",
        SimpleNamespace(lookup_native_reference=lookup),
    )
    assert main(arguments(tmp_path) + ["--execute"]) == expected
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == status
    assert result["reason_code"] == "EXACT_READER_REASON"
    assert result["canonical_contract_id"] is None
    assert result["publication_asserted"] is False
    assert closed == list(reversed(opened))


def test_same_database_rejected(tmp_path):
    args = arguments(tmp_path)
    args[3] = args[1]
    with pytest.raises(SystemExit):
        main(args)


def test_connection_failure_redacted(tmp_path, monkeypatch, capsys):
    for name in ("bronze.duckdb", "silver.duckdb"):
        (tmp_path / name).touch()

    def connect(*args, **kwargs):
        raise RuntimeError("SECRET_PAYLOAD_MUST_NOT_ESCAPE")

    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=connect))
    monkeypatch.setitem(
        sys.modules,
        "nse_quant.data_platform.native_reference_reader",
        SimpleNamespace(lookup_native_reference=None),
    )
    assert main(arguments(tmp_path) + ["--execute"]) == 1
    output = capsys.readouterr().out
    assert "SECRET" not in output
    assert json.loads(output)["reason_code"] == "REFERENCE_LOOKUP_FAILED"


def test_real_duckdb_connections_are_read_only(tmp_path, monkeypatch, capsys):
    import duckdb

    for name in ("bronze.duckdb", "silver.duckdb"):
        connection = duckdb.connect(str(tmp_path / name))
        connection.execute("CREATE TABLE evidence (id INTEGER)")
        connection.close()

    @dataclass
    class Result:
        status: str = "blocked"
        reason_code: str = "TEST_READ_ONLY_BOUNDARY"

    def lookup(bronze, silver, **kwargs):
        for connection in (bronze, silver):
            assert connection.execute("SELECT count(*) FROM evidence").fetchone() == (0,)
            with pytest.raises(duckdb.InvalidInputException):
                connection.execute("INSERT INTO evidence VALUES (1)")
        return Result()

    monkeypatch.setitem(
        sys.modules,
        "nse_quant.data_platform.native_reference_reader",
        SimpleNamespace(lookup_native_reference=lookup),
    )
    assert main(arguments(tmp_path) + ["--execute"]) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "TEST_READ_ONLY_BOUNDARY"
