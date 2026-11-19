"""Plan/diagnostic tests and real disposable DuckDB handle tests, not native IV E2E."""

import builtins
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import research_iv_bundle_inspect_cli as cli


def arguments(paths=None):
    chosen = paths or tuple("missing-" + name + ".duckdb" for name in cli.PATH_NAMES)
    result: list[str] = []
    for name, value in zip(cli.PATH_NAMES, chosen, strict=True):
        result.extend(("--" + name, value))
    return result + ["--build-id-pin", "a" * 64, "--archive-fingerprint", "b" * 64]


def negative_summary(**changes):
    fields: dict[str, Any] = dict.fromkeys((*cli.OBSERVATION_FLAGS, *cli.DENIAL_FLAGS), False)
    fields.update(
        version=cli.SERVICE_VERSION,
        build_id="a" * 64,
        expected_archive_fingerprint="b" * 64,
        status="review_required",
        reason_codes=("SYNTHETIC_NEGATIVE_DIAGNOSTIC",),
        bundle_id=None,
        evidence_fingerprint=None,
        canonical_contract_id=None,
    )
    fields.update(changes)
    return SimpleNamespace(**fields)


def test_plan_does_no_io_path_probing_or_execution_imports(monkeypatch, capsys):
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "duckdb" or name.startswith(
            (
                "nse_quant.data_platform.research_iv_bundle_revalidation",
                "nse_quant.data_platform.native_research",
                "scipy",
                "socket",
                "keyring",
            )
        ):
            raise AssertionError("Plan imported execution dependency")
        return real_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("Plan performed I/O")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", guarded)
        patch.setattr(builtins, "open", forbidden)
        for method in ("open", "resolve", "exists", "is_file", "stat", "samefile", "absolute"):
            patch.setattr(Path, method, forbidden)
        assert cli.main(arguments()) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "PLANNED"
    assert value["plan"]["inputs_verified"] is False
    assert value["plan"]["current_source_checked"] is False
    assert value["plan"]["publication_requested"] is False
    assert value["plan"]["decision_eligibility_asserted"] is False
    assert len(value["plan"]["paths_as_supplied"]) == 7


def test_plan_keeps_literal_paths_and_reviewed_pins(capsys):
    paths = tuple("relative/../path-" + str(index) for index in range(7))
    assert cli.main(arguments(paths)) == 0
    plan = json.loads(capsys.readouterr().out)["plan"]
    assert tuple(plan["paths_as_supplied"][name] for name in cli.PATH_NAMES) == paths
    assert plan["build_id_pin"] == "a" * 64
    assert plan["expected_archive_fingerprint"] == "b" * 64


@pytest.mark.parametrize(
    "pin", ["short", "A" * 64, "a" * 63, "g" * 64], ids=["short", "upper", "length", "hex"]
)
def test_bad_pins_rejected_before_any_path_work(monkeypatch, pin):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid pin reached path work")

    monkeypatch.setattr(Path, "is_file", forbidden)
    args = arguments() + ["--execute"]
    args[args.index("--build-id-pin") + 1] = pin
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2


@pytest.mark.parametrize(
    "bad", ["", "x" * 4097, "nul\x00path", "line\npath"], ids=["empty", "long", "nul", "newline"]
)
def test_path_strings_bounded_without_probing(bad):
    paths = ["missing"] * 7
    paths[0] = bad
    with pytest.raises(SystemExit) as error:
        cli.main(arguments(tuple(paths)))
    assert error.value.code == 2


def test_execute_missing_files_does_not_create_them(tmp_path, capsys):
    paths = tuple(str(tmp_path / (str(index) + ".duckdb")) for index in range(7))
    assert cli.main(arguments(paths) + ["--execute"]) == 1
    assert not any(Path(raw).exists() for raw in paths)
    assert json.loads(capsys.readouterr().out) == {
        "status": "FAILED",
        "reason_code": "IV_BUNDLE_INSPECTION_FAILED",
    }


def test_filesystem_exception_text_never_leaks(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise OSError("SYNTHETIC_SECRET_RAW_PAYLOAD")

    monkeypatch.setattr(Path, "is_file", fail)
    assert cli.main(arguments() + ["--execute"]) == 1
    captured = capsys.readouterr()
    assert "SYNTHETIC_SECRET" not in captured.out + captured.err
    assert json.loads(captured.out)["reason_code"] == "IV_BUNDLE_INSPECTION_FAILED"


@pytest.fixture
def databases(tmp_path):
    paths = tuple(str(tmp_path / ("safe-" + str(index) + ".duckdb")) for index in range(7))
    for raw in paths:
        with duckdb.connect(raw) as conn:
            row = conn.execute("SELECT current_database()").fetchone()
            assert row is not None
            catalog = '"' + str(row[0]).replace('"', '""') + '"'
            conn.execute(f'CREATE TABLE {catalog}."main"."synthetic_marker" (value INTEGER)')
    return paths


def test_seven_real_readonly_handles_and_cleanup(databases):
    with cli._open_inputs(databases) as handles:
        assert len(handles) == 7 and len({id(conn) for conn in handles}) == 7
        for conn in handles:
            assert conn.execute("SELECT 1").fetchone() == (1,)
            row = conn.execute("SELECT current_database()").fetchone()
            assert row is not None
            catalog = '"' + str(row[0]).replace('"', '""') + '"'
            with pytest.raises(duckdb.Error):
                conn.execute(f'CREATE SCHEMA {catalog}."forbidden_write"')
    for conn in handles:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_supported_source_aliases_reuse_one_live_handle(databases):
    paths = (databases[0],) * 5 + databases[5:]
    with cli._open_inputs(paths) as handles:
        assert all(conn is handles[0] for conn in handles[:5])
        assert handles[5] is not handles[0] and handles[6] is not handles[5]


@pytest.mark.parametrize("role", range(6), ids=["bronze", "frame", "ref", "audit", "gold", "iv"])
def test_bundle_archive_source_alias_rejected_before_connection(databases, monkeypatch, role):
    paths = list(databases)
    paths[role] = paths[6]

    def forbidden(*args, **kwargs):
        raise AssertionError("Archive alias reached connect")

    monkeypatch.setattr(duckdb, "connect", forbidden)
    with (
        pytest.raises(ValueError, match="SEPARATE_IV_BUNDLE_ARCHIVE"),
        cli._open_inputs(tuple(paths)),
    ):
        raise AssertionError("Unexpected context entry")


@pytest.mark.parametrize("role", range(5), ids=["bronze", "frame", "ref", "audit", "gold"])
def test_member_archive_source_alias_rejected(databases, role):
    paths = list(databases)
    paths[role] = paths[5]
    with (
        pytest.raises(ValueError, match="SEPARATE_IV_MEMBER_ARCHIVE"),
        cli._open_inputs(tuple(paths)),
    ):
        raise AssertionError("Unexpected context entry")


def test_real_hardlink_source_alias_reuses_handle(databases, tmp_path):
    import os

    alias = tmp_path / "safe-hardlink.duckdb"
    os.link(databases[0], alias)
    paths = (databases[0], str(alias), *databases[2:])
    with cli._open_inputs(paths) as handles:
        assert handles[0] is handles[1]


def test_corrupt_later_database_closes_prior_real_handles(databases, monkeypatch):
    Path(databases[-1]).write_bytes(b"synthetic corrupt database")
    real = duckdb.connect
    opened = []

    def observe(*args, **kwargs):
        assert kwargs == {"read_only": True}
        conn = real(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(duckdb, "connect", observe)
    with pytest.raises(duckdb.Error), cli._open_inputs(databases):
        raise AssertionError("Corrupt database unexpectedly opened")
    assert len(opened) == 6
    for conn in opened:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_negative_summary_is_bounded_and_omits_nested_payloads():
    result = negative_summary(
        raw_payload="SYNTHETIC_SECRET",
        archive_before="RAW",
        fresh_before="RAW",
    )
    raw, exit_code = cli._summary(result, "a" * 64, "b" * 64)
    value = json.loads(raw)
    assert exit_code == 2 and value["status"] == "review_required"
    assert len(raw.encode()) <= cli.MAX_SUMMARY_BYTES
    assert "SYNTHETIC_SECRET" not in raw and "archive_before" not in raw
    assert value["bundle_id"] is None and value["decision_eligibility_asserted"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"version": "unknown@2"},
        {"publication_asserted": True},
        {"current_source_checked": 1},
        {"reason_codes": ("raw secret text",)},
        {"reason_codes": ("DUPLICATE", "DUPLICATE")},
        {"bundle_id": "c" * 64},
        {"status": "matched_current_research_iv_bundle"},
        {"build_id": "c" * 64},
        {"expected_archive_fingerprint": "c" * 64},
        {"canonical_contract_id": "invented"},
    ],
    ids=[
        "version",
        "authority",
        "bool",
        "reason",
        "duplicate",
        "bundle",
        "incomplete-positive",
        "record-pin",
        "archive-pin",
        "identity",
    ],
)
def test_bad_or_escalated_diagnostic_results_rejected(change):
    with pytest.raises(ValueError):
        cli._summary(negative_summary(**change), "a" * 64, "b" * 64)


def test_summary_budget_cannot_return_truncated_success(monkeypatch):
    monkeypatch.setattr(cli, "MAX_SUMMARY_BYTES", 1)
    with pytest.raises(ValueError, match="SUMMARY_BYTE_LIMIT"):
        cli._summary(negative_summary(), "a" * 64, "b" * 64)
