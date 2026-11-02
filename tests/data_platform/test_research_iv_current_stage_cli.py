"""Plan/negative diagnostic and real disposable read-only connection tests, not native E2E."""

import builtins
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import research_iv_current_stage_cli as cli


def arguments(paths=None, root="missing-root"):
    selected = paths or tuple("missing-" + str(index) + ".duckdb" for index in range(8))
    args: list[str] = []
    for name, path in zip(cli.PATH_NAMES, selected, strict=True):
        args.extend(("--" + name, path))
    return args + [
        "--artifact-root",
        root,
        "--stage-build-id-pin",
        "a" * 64,
        "--stage-fingerprint",
        "b" * 64,
    ]


def negative_result(**changes):
    values: dict[str, Any] = dict.fromkeys((*cli.OBSERVATION_FLAGS, *cli.DENIAL_FLAGS), False)
    values.update(
        version=cli.SERVICE_VERSION,
        stage_build_id="a" * 64,
        expected_stage_fingerprint="b" * 64,
        status="review_required",
        reason_codes=("SYNTHETIC_NEGATIVE_DIAGNOSTIC",),
        bundle_id=None,
        evidence_fingerprint=None,
        canonical_contract_id=None,
        event_ts=None,
        published_at=None,
    )
    values.update(changes)
    return SimpleNamespace(**values)


def test_plan_performs_no_io_or_execution_imports(monkeypatch, capsys):
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "duckdb" or name.startswith(
            (
                "nse_quant.data_platform.research_iv_stage_revalidation",
                "scipy",
                "socket",
                "keyring",
            )
        ):
            raise AssertionError("Plan imported execution dependency")
        return real_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("Plan probed/opened a path")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", guarded)
        patch.setattr(builtins, "open", forbidden)
        for method in ("open", "exists", "resolve", "is_file", "is_dir", "stat", "samefile"):
            patch.setattr(Path, method, forbidden)
        assert cli.main(arguments(root="literal/../missing-root")) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "PLANNED"
    assert value["plan"]["artifact_root_as_supplied"] == "literal/../missing-root"
    assert len(value["plan"]["paths_as_supplied"]) == 8
    assert value["plan"]["inputs_verified"] is False
    assert value["plan"]["current_source_checked"] is False
    assert value["plan"]["decision_eligibility_asserted"] is False


@pytest.mark.parametrize(
    "field", ["--stage-build-id-pin", "--stage-fingerprint"], ids=["stage", "fingerprint"]
)
@pytest.mark.parametrize("bad", ["bad", "A" * 64, "g" * 64], ids=["short", "upper", "hex"])
def test_exact_review_pins_checked_before_io(monkeypatch, field, bad):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid pin reached path probe")

    monkeypatch.setattr(Path, "is_file", forbidden)
    args = arguments() + ["--execute"]
    args[args.index(field) + 1] = bad
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2


@pytest.mark.parametrize("bad", ["", "x" * 2049, "bad\nroot"], ids=["empty", "long", "control"])
def test_plan_root_bounds(bad):
    with pytest.raises(SystemExit) as error:
        cli.main(arguments(root=bad))
    assert error.value.code == 2


def test_execute_missing_files_does_not_create_anything(tmp_path, capsys):
    paths = tuple(str(tmp_path / (str(index) + ".duckdb")) for index in range(8))
    assert cli.main(arguments(paths, str(tmp_path / "absent")) + ["--execute"]) == 1
    assert not list(tmp_path.iterdir())
    assert json.loads(capsys.readouterr().out) == {
        "status": "FAILED",
        "reason_code": "IV_CURRENT_STAGE_INSPECTION_FAILED",
    }


def test_filesystem_failure_is_sanitized(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise OSError("SYNTHETIC_SECRET_PAYLOAD")

    monkeypatch.setattr(Path, "is_file", fail)
    assert cli.main(arguments() + ["--execute"]) == 1
    captured = capsys.readouterr()
    assert "SYNTHETIC_SECRET" not in captured.out + captured.err
    assert json.loads(captured.out)["status"] == "FAILED"


@pytest.fixture
def databases(tmp_path):
    paths = tuple(str(tmp_path / ("source-" + str(index) + ".duckdb")) for index in range(8))
    for raw in paths:
        with duckdb.connect(raw) as conn:
            catalog = conn.execute("SELECT current_database()").fetchone()
            assert catalog is not None
            quoted = '"' + str(catalog[0]).replace('"', '""') + '"'
            conn.execute(f'CREATE TABLE {quoted}."main"."synthetic_marker" (value INTEGER)')
    root = tmp_path / "artifacts"
    root.mkdir()
    return paths, root


def test_eight_actual_readonly_handles_and_closure(databases):
    paths, root = databases
    with cli._open_inputs(paths, root) as handles:
        assert len(handles) == len({id(conn) for conn in handles}) == 8
        for conn in handles:
            catalog = conn.execute("SELECT current_database()").fetchone()
            assert catalog is not None
            quoted = '"' + str(catalog[0]).replace('"', '""') + '"'
            with pytest.raises(duckdb.Error):
                conn.execute(f'CREATE SCHEMA {quoted}."forbidden_write"')
    for conn in handles:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_supported_source_aliases_share_one_actual_handle(databases):
    paths, root = databases
    selected = (paths[0],) * 5 + paths[5:]
    with cli._open_inputs(selected, root) as handles:
        assert all(conn is handles[0] for conn in handles[:5])
        assert len({id(conn) for conn in handles}) == 4


ARCHIVE_ALIASES = [(role, source) for role in (5, 6, 7) for source in range(role)]


@pytest.mark.parametrize(
    "pair", ARCHIVE_ALIASES, ids=[f"role{role}-source{source}" for role, source in ARCHIVE_ALIASES]
)
def test_every_archive_role_alias_rejected_before_connect(databases, monkeypatch, pair):
    paths, root = databases
    chosen = list(paths)
    role, source = pair
    chosen[role] = chosen[source]

    def forbidden(*args, **kwargs):
        raise AssertionError("Archive role alias reached connect")

    monkeypatch.setattr(duckdb, "connect", forbidden)
    with pytest.raises(ValueError, match="SEPARATE_IV_"), cli._open_inputs(tuple(chosen), root):
        raise AssertionError("Unexpected context entry")


def test_actual_hardlink_source_alias_reused(databases, tmp_path):
    paths, root = databases
    alias = tmp_path / "safe-hardlink.duckdb"
    os.link(paths[0], alias)
    chosen = (paths[0], str(alias), *paths[2:])
    with cli._open_inputs(chosen, root) as handles:
        assert handles[0] is handles[1]


def test_root_containing_database_rejected_before_open(databases, monkeypatch):
    paths, root = databases

    def forbidden(*args, **kwargs):
        raise AssertionError("Overlapping artifact root reached connect")

    monkeypatch.setattr(duckdb, "connect", forbidden)
    with pytest.raises(ValueError, match="PATH_OVERLAP"), cli._open_inputs(paths, root.parent):
        raise AssertionError("Unexpected context entry")


def test_missing_relative_and_redirected_roots_do_not_open_db(databases, monkeypatch):
    paths, root = databases
    for candidate in (root / "absent", Path("relative")):
        with pytest.raises(ValueError), cli._open_inputs(paths, candidate):
            raise AssertionError("Unexpected context entry")
    real = Path.is_junction

    def redirected(path):
        return path == root or real(path)

    monkeypatch.setattr(Path, "is_junction", redirected)
    with pytest.raises(ValueError, match="REDIRECTED"), cli._open_inputs(paths, root):
        raise AssertionError("Unexpected context entry")


def test_corrupt_eighth_file_closes_seven_real_opened_handles(databases, monkeypatch):
    paths, root = databases
    Path(paths[-1]).write_bytes(b"synthetic corrupt database")
    real = duckdb.connect
    opened: list[duckdb.DuckDBPyConnection] = []

    def observe(*args, **kwargs):
        assert kwargs == {"read_only": True}
        conn = real(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(duckdb, "connect", observe)
    with pytest.raises(duckdb.Error), cli._open_inputs(paths, root):
        raise AssertionError("Corrupt file unexpectedly opened")
    assert len(opened) == 7
    for conn in opened:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_review_summary_keeps_partial_facts_without_nested_data():
    value = negative_result(
        current_source_checked=True,
        recorded_native_digests_matched=True,
        stage_before="SYNTHETIC_SECRET",
        fresh_before="SYNTHETIC_SECRET",
    )
    raw, code = cli._summary(value, "a" * 64, "b" * 64)
    result = json.loads(raw)
    assert code == 2 and result["current_source_checked"] is True
    assert result["recorded_native_digests_matched"] is True
    assert result["stage_unchanged_observed"] is False
    assert result["bundle_id"] is None and result["evidence_fingerprint"] is None
    assert "SYNTHETIC_SECRET" not in raw and "stage_before" not in result


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "unknown@2"},
        {"stage_build_id": "c" * 64},
        {"expected_stage_fingerprint": "c" * 64},
        {"publication_asserted": True},
        {"current_source_checked": 1},
        {"reason_codes": ("raw text",)},
        {"reason_codes": ("DUPLICATE", "DUPLICATE")},
        {"bundle_id": "c" * 64},
        {"status": "matched_current_research_iv_stage"},
        {"event_ts": "invented"},
        {"published_at": "invented"},
        {"canonical_contract_id": "invented"},
    ],
    ids=[
        "version",
        "id",
        "review-pin",
        "authority",
        "bool",
        "reason",
        "duplicate",
        "bundle",
        "incomplete-positive",
        "event",
        "published",
        "identity",
    ],
)
def test_malformed_or_escalated_diagnostic_is_rejected(changes):
    with pytest.raises(ValueError):
        cli._summary(negative_result(**changes), "a" * 64, "b" * 64)


def test_diagnostic_limit_never_returns_truncated_result(monkeypatch):
    monkeypatch.setattr(cli, "MAX_SUMMARY_BYTES", 1)
    with pytest.raises(ValueError, match="DIAGNOSTIC_LIMIT"):
        cli._summary(negative_result(), "a" * 64, "b" * 64)
