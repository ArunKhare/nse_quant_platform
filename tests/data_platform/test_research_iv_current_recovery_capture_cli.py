"""Plan/diagnostic policy and actual disposable read-only DuckDB I/O. Not native E2E."""

import builtins
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import research_iv_current_recovery_capture_cli as cli


def arguments(staging="missing-stage", capture="missing-capture", root="missing-root"):
    return [
        "--staging-db",
        staging,
        "--capture-db",
        capture,
        "--artifact-root",
        root,
        "--capture-build-id-pin",
        "a" * 64,
        "--capture-fingerprint",
        "b" * 64,
    ]


def diagnostic(**changes):
    value: dict[str, Any] = dict.fromkeys((*cli.OBSERVATION_FLAGS, *cli.DENIAL_FLAGS), False)
    value.update(dict.fromkeys(cli.NULL_FIELDS))
    value.update(
        version=cli.SERVICE_VERSION,
        capture_build_id="a" * 64,
        expected_capture_fingerprint="b" * 64,
        status="review_required",
        reason_codes=("SYNTHETIC_DIAGNOSTIC",),
        plan_evidence_fingerprint=None,
        evidence_fingerprint=None,
    )
    value.update(changes)
    return SimpleNamespace(**value)


def test_default_plan_has_no_io_or_execution_imports(monkeypatch, capsys):
    real_import = builtins.__import__

    def guard(name, *args, **kwargs):
        if name == "duckdb" or name.startswith(
            (
                "nse_quant.data_platform.research_iv_recovery_capture",
                "nse_quant.data_platform.research_iv_recovery_plan",
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
        patch.setattr(builtins, "__import__", guard)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(os, "scandir", forbidden)
        for name in ("open", "resolve", "exists", "is_file", "is_dir", "stat", "samefile"):
            patch.setattr(Path, name, forbidden)
        assert cli.main(arguments(root="literal/../missing-root")) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PLANNED"
    assert result["plan"]["artifact_root_as_supplied"] == "literal/../missing-root"
    assert result["plan"]["inputs_verified"] is False
    assert result["plan"]["current_reconciliation_checked"] is False
    assert all(result["plan"][name] is False for name in cli.DENIAL_FLAGS)


@pytest.mark.parametrize(
    "field", ["--capture-build-id-pin", "--capture-fingerprint"], ids=["id", "fingerprint"]
)
@pytest.mark.parametrize(
    "bad", ["", "a" * 63, "A" * 64, "g" * 64], ids=["empty", "short", "upper", "hex"]
)
def test_reviewed_pins_validate_before_probes(monkeypatch, field, bad):
    def forbidden(*args, **kwargs):
        raise AssertionError("Bad pin reached probe")

    monkeypatch.setattr(Path, "is_file", forbidden)
    args = arguments() + ["--execute"]
    args[args.index(field) + 1] = bad
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2


@pytest.mark.parametrize(
    "field,limit",
    [("--staging-db", 4096), ("--capture-db", 4096), ("--artifact-root", 2048)],
    ids=["stage", "capture", "root"],
)
@pytest.mark.parametrize("kind", ["empty", "control", "long"])
def test_literal_path_bounds(field, limit, kind):
    args = arguments()
    args[args.index(field) + 1] = {
        "empty": "",
        "control": "private\npath",
        "long": "x" * (limit + 1),
    }[kind]
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2


def test_missing_execution_inputs_not_created(tmp_path, capsys):
    args = arguments(str(tmp_path / "stage"), str(tmp_path / "capture"), str(tmp_path / "root"))
    assert cli.main(args + ["--execute"]) == 1
    assert not list(tmp_path.iterdir())
    assert json.loads(capsys.readouterr().out) == {
        "status": "FAILED",
        "reason_code": "IV_CURRENT_RECOVERY_CAPTURE_INSPECTION_FAILED",
    }


def test_failure_diagnostic_sanitized(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise OSError("PRIVATE_EXCEPTION_PAYLOAD")

    monkeypatch.setattr(Path, "is_file", fail)
    assert cli.main(arguments() + ["--execute"]) == 1
    captured = capsys.readouterr()
    assert "PRIVATE_EXCEPTION_PAYLOAD" not in captured.out + captured.err


@pytest.fixture
def databases(tmp_path):
    paths = (tmp_path / "stage.duckdb", tmp_path / "capture.duckdb")
    for path in paths:
        with duckdb.connect(str(path)) as conn:
            row = conn.execute("SELECT current_database()").fetchone()
            assert row is not None
            catalog = '"' + str(row[0]).replace('"', '""') + '"'
            conn.execute(f'CREATE TABLE {catalog}."main"."synthetic" (value INTEGER)')
    root = tmp_path / "artifacts"
    root.mkdir()
    return paths, root


def test_two_actual_readonly_connections_and_normal_closure(databases):
    paths, root = databases
    with cli._open_inputs(str(paths[0]), str(paths[1]), root) as handles:
        assert handles[0] is not handles[1]
        for conn in handles:
            row = conn.execute("SELECT current_database()").fetchone()
            assert row is not None
            catalog = '"' + str(row[0]).replace('"', '""') + '"'
            with pytest.raises(duckdb.Error):
                conn.execute(f'CREATE SCHEMA {catalog}."forbidden"')
    for conn in handles:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_body_exception_closes_both_handles(databases):
    paths, root = databases
    with (
        pytest.raises(RuntimeError, match="synthetic"),
        cli._open_inputs(
            str(paths[0]),
            str(paths[1]),
            root,
        ) as handles,
    ):
        raise RuntimeError("synthetic")
    for conn in handles:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_same_file_and_hardlink_alias_rejected_before_connect(databases, tmp_path, monkeypatch):
    paths, root = databases
    alias = tmp_path / "hardlink.duckdb"
    os.link(paths[0], alias)

    def forbidden(*args, **kwargs):
        raise AssertionError("Alias reached connect")

    monkeypatch.setattr(duckdb, "connect", forbidden)
    for second in (paths[0], alias):
        with (
            pytest.raises(ValueError, match="SEPARATE_"),
            cli._open_inputs(
                str(paths[0]),
                str(second),
                root,
            ),
        ):
            raise AssertionError("Alias accepted")


def test_root_overlap_and_hardlinked_database_rejected(databases, monkeypatch):
    paths, root = databases

    def forbidden(*args, **kwargs):
        raise AssertionError("Root overlap reached connect")

    monkeypatch.setattr(duckdb, "connect", forbidden)
    with (
        pytest.raises(ValueError, match="ROOT_OVERLAP"),
        cli._open_inputs(
            str(paths[0]),
            str(paths[1]),
            root.parent,
        ),
    ):
        raise AssertionError("Root overlap accepted")
    os.link(paths[0], root / "database-hardlink")
    with (
        pytest.raises(ValueError, match="ARTIFACT_HARDLINK"),
        cli._open_inputs(
            str(paths[0]),
            str(paths[1]),
            root,
        ),
    ):
        raise AssertionError("Hardlink accepted")


def test_corrupt_second_file_closes_first_handle(databases, monkeypatch):
    paths, root = databases
    paths[1].write_bytes(b"synthetic corrupt database")
    real = duckdb.connect
    opened: list[duckdb.DuckDBPyConnection] = []

    def connect(*args, **kwargs):
        assert kwargs == {"read_only": True}
        conn = real(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(duckdb, "connect", connect)
    with pytest.raises(duckdb.Error), cli._open_inputs(str(paths[0]), str(paths[1]), root):
        raise AssertionError("Corrupt database accepted")
    assert len(opened) == 1
    with pytest.raises(duckdb.Error):
        opened[0].execute("SELECT 1")


def test_redirected_root_and_entry_rejected_without_body_reads(databases, monkeypatch):
    paths, root = databases
    real = Path.is_junction

    def redirected(path):
        return path == root or real(path)

    monkeypatch.setattr(Path, "is_junction", redirected)
    with (
        pytest.raises(ValueError, match="REDIRECTED_ROOT"),
        cli._open_inputs(
            str(paths[0]),
            str(paths[1]),
            root,
        ),
    ):
        raise AssertionError("Redirected root accepted")
    marker = root / "private-foreign"
    marker.write_bytes(b"retain")

    def entry_redirect(path):
        return path == marker or real(path)

    monkeypatch.setattr(Path, "is_junction", entry_redirect)
    with (
        pytest.raises(ValueError, match="REDIRECTED_ENTRY"),
        cli._open_inputs(
            str(paths[0]),
            str(paths[1]),
            root,
        ),
    ):
        raise AssertionError("Redirected entry accepted")
    assert marker.read_bytes() == b"retain"


def test_entry_budget_is_not_an_accepted_prefix(databases, monkeypatch):
    paths, root = databases
    monkeypatch.setattr(cli, "MAX_ROOT_ENTRIES", 1)
    (root / "one").write_bytes(b"private")
    (root / "two").write_bytes(b"private")
    with (
        pytest.raises(ValueError, match="ENTRY_LIMIT"),
        cli._open_inputs(
            str(paths[0]),
            str(paths[1]),
            root,
        ),
    ):
        raise AssertionError("Oversized root accepted")


def test_diagnostic_review_keeps_partial_facts_not_nested_payloads():
    value = diagnostic(
        archived_recording_verified=True,
        current_reconciliation_checked=True,
        exact_recorded_plan_reproduced=True,
        fresh_before="PRIVATE_NESTED_PAYLOAD",
    )
    raw, code = cli._summary(value, "a" * 64, "b" * 64)
    result = json.loads(raw)
    assert code == 2 and result["exact_recorded_plan_reproduced"] is True
    assert result["capture_unchanged_observed"] is False
    assert result["evidence_fingerprint"] is None
    assert "PRIVATE_NESTED_PAYLOAD" not in raw and "fresh_before" not in result


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "unknown@2"},
        {"capture_build_id": "c" * 64},
        {"expected_capture_fingerprint": "c" * 64},
        {"current_source_checked": True},
        {"recovery_execution_authorized": True},
        {"publication_asserted": True},
        {"current_reconciliation_checked": 1},
        {"reason_codes": ("private text",)},
        {"reason_codes": ("DUPLICATE", "DUPLICATE")},
        {"reason_codes": ()},
        {"evidence_fingerprint": "c" * 64},
        {"plan_evidence_fingerprint": "c" * 64},
        {"status": "matched_current_research_iv_recovery_capture"},
        {"event_ts": "invented"},
        {"canonical_contract_id": "invented"},
        {"current_reconciliation_checked": True},
    ],
    ids=[
        "version",
        "id",
        "pin",
        "pricing",
        "recovery",
        "publication",
        "bool",
        "reason",
        "duplicate",
        "empty",
        "evidence",
        "plan",
        "incomplete",
        "time",
        "identity",
        "facts",
    ],
)
def test_diagnostic_escalation_or_malformed_contract_rejected(changes):
    with pytest.raises(ValueError):
        cli._summary(diagnostic(**changes), "a" * 64, "b" * 64)


def test_diagnostic_byte_limit_not_truncated(monkeypatch):
    monkeypatch.setattr(cli, "MAX_SUMMARY_BYTES", 1)
    with pytest.raises(ValueError, match="SUMMARY_LIMIT"):
        cli._summary(diagnostic(), "a" * 64, "b" * 64)


def test_positive_projection_requires_all_facts_and_ids():
    # Projection contract test ONLY: not a mocked native computation or CLI success.
    value = diagnostic(
        **dict.fromkeys(cli.OBSERVATION_FLAGS, True),
        status="matched_current_research_iv_recovery_capture",
        plan_evidence_fingerprint="c" * 64,
        evidence_fingerprint="d" * 64,
    )
    raw, code = cli._summary(value, "a" * 64, "b" * 64)
    result = json.loads(raw)
    assert code == 0 and result["current_source_checked"] is False
    assert result["read_only_execution"] is True


def test_missing_and_relative_roots_reject_before_connect(databases, monkeypatch):
    paths, root = databases

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid root reached connect")

    monkeypatch.setattr(duckdb, "connect", forbidden)
    for candidate in (Path("relative"), root / "missing", root / ".." / "ambiguous"):
        with pytest.raises(ValueError), cli._open_inputs(str(paths[0]), str(paths[1]), candidate):
            raise AssertionError("Invalid root accepted")


def test_root_preflight_does_not_read_foreign_or_pending_bodies(databases, monkeypatch):
    paths, root = databases
    for name in ("private-foreign", ".pending-iv-private"):
        (root / name).write_bytes(b"private body must not be read")

    def forbidden(*args, **kwargs):
        raise AssertionError("Preflight opened a body")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(os, "open", forbidden)
    # Synthetic DB context only: a real stage/codec would reject foreign root content.
    with cli._open_inputs(str(paths[0]), str(paths[1]), root) as handles:
        assert all(conn.execute("SELECT 1").fetchone() == (1,) for conn in handles)
