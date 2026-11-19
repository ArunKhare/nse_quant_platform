"""No-I/O plans, negative diagnostic contracts, real disposable read-only DB checks."""

import builtins
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import research_iv_current_stress_archive_cli as cli

PINS = ("a" * 64, "b" * 64)


def arguments(paths=None):
    chosen = paths or tuple("missing-" + str(i) for i in range(7))
    args: list[str] = []
    for name, path in zip(cli.PATH_NAMES, chosen, strict=True):
        args.extend(("--" + name, path))
    return args + ["--stress-record-id-pin", PINS[0], "--recording-fingerprint", PINS[1]]


def negative(**changes):
    value: dict[str, Any] = dict.fromkeys((*cli.OBSERVATION_FLAGS, *cli.DENIAL_FLAGS), False)
    value.update(
        dict.fromkeys(
            (*cli.NULL_FIELDS, "study", "native_stress_fingerprint", "evidence_fingerprint")
        )
    )
    value.update(
        version=cli.SERVICE_VERSION,
        stress_record_id=PINS[0],
        expected_recording_fingerprint=PINS[1],
        status="review_required",
        reason_codes=("SYNTHETIC_DIAGNOSTIC",),
    )
    value.update(changes)
    return SimpleNamespace(**value)


def test_plan_no_io_or_native_execution_imports(monkeypatch, capsys):
    real = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "duckdb" or name.startswith(
            (
                "scipy",
                "socket",
                "keyring",
                "nse_quant.data_platform.research_iv_stress_archive",
                "nse_quant.data_platform.native_research_iv_spot_stress",
                "nse_quant.data_platform.research_iv_spot_stress",
            )
        ):
            raise AssertionError("Plan imported execution module")
        return real(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("Plan probed/opened a path")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", guarded)
        patch.setattr(builtins, "open", forbidden)
        for method in ("open", "stat", "resolve", "exists", "is_file", "samefile"):
            patch.setattr(Path, method, forbidden)
        assert cli.main(arguments(("literal/../unverified",) * 7)) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "PLANNED"
    assert all(p == "literal/../unverified" for p in value["plan"]["paths_as_supplied"].values())
    assert value["plan"]["inputs_verified"] is False
    assert value["plan"]["current_source_checked"] is False
    assert value["plan"]["model_computation_rechecked"] is False


@pytest.mark.parametrize(
    "field", ["--stress-record-id-pin", "--recording-fingerprint"], ids=["record", "fingerprint"]
)
@pytest.mark.parametrize(
    "bad", ["", "a" * 63, "A" * 64, "g" * 64], ids=["empty", "short", "upper", "hex"]
)
def test_exact_reviewed_pins_validate_before_paths(field, bad, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid pin reached filesystem")

    monkeypatch.setattr(Path, "is_file", forbidden)
    args = arguments() + ["--execute"]
    args[args.index(field) + 1] = bad
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2


@pytest.mark.parametrize("bad", ["", "x" * 4097, "private\npath"], ids=["empty", "long", "control"])
def test_literal_path_bounds(bad):
    args = arguments()
    args[1] = bad
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2


def test_caller_cannot_replace_frozen_shocks_or_native_pins():
    with pytest.raises(SystemExit) as error:
        cli.main(arguments() + ["--shock-bps", "0"])
    assert error.value.code == 2


def test_missing_execute_inputs_not_created(tmp_path, capsys):
    paths = tuple(str(tmp_path / (str(i) + ".duckdb")) for i in range(7))
    assert cli.main(arguments(paths) + ["--execute"]) == 1
    assert list(tmp_path.iterdir()) == []
    assert json.loads(capsys.readouterr().out) == {
        "status": "FAILED",
        "reason_code": "IV_CURRENT_STRESS_INSPECTION_FAILED",
    }


def test_sanitized_filesystem_failure(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise OSError("PRIVATE_PATH_OR_PAYLOAD")

    monkeypatch.setattr(Path, "is_file", fail)
    assert cli.main(arguments() + ["--execute"]) == 1
    captured = capsys.readouterr()
    assert "PRIVATE_PATH_OR_PAYLOAD" not in captured.out + captured.err


@pytest.fixture
def databases(tmp_path):
    paths = tuple(str(tmp_path / (str(i) + ".duckdb")) for i in range(7))
    for path in paths:
        with duckdb.connect(path) as conn:
            row = conn.execute("SELECT current_database()").fetchone()
            assert row is not None
            catalog = '"' + str(row[0]).replace('"', '""') + '"'
            conn.execute(f'CREATE TABLE {catalog}."main"."synthetic" (v INTEGER)')
    return paths


def test_actual_seven_readonly_handles_and_close(databases):
    with cli._open_inputs(databases) as handles:
        assert len(handles) == len({id(conn) for conn in handles}) == 7
        for conn in handles:
            row = conn.execute("SELECT current_database()").fetchone()
            assert row is not None
            catalog = '"' + str(row[0]).replace('"', '""') + '"'
            with pytest.raises(duckdb.Error):
                conn.execute(f'CREATE SCHEMA {catalog}."forbidden"')
    for conn in handles:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_supported_first_five_aliases_reuse_one_handle(databases):
    paths = (databases[0],) * 5 + databases[5:]
    with cli._open_inputs(paths) as handles:
        assert all(conn is handles[0] for conn in handles[:5])
        assert len({id(conn) for conn in handles}) == 3


ALIASES = [(role, prior) for role in (5, 6) for prior in range(role)]


@pytest.mark.parametrize(
    "pair", ALIASES, ids=[f"role{role}-prior{prior}" for role, prior in ALIASES]
)
def test_all_archive_aliases_rejected_before_connect(databases, monkeypatch, pair):
    role, prior = pair
    paths = list(databases)
    paths[role] = paths[prior]

    def forbidden(*args, **kwargs):
        raise AssertionError("Archive alias reached connect")

    monkeypatch.setattr(duckdb, "connect", forbidden)
    with pytest.raises(ValueError, match="SEPARATE_CURRENT_STRESS"), cli._open_inputs(tuple(paths)):
        raise AssertionError("Archive alias accepted")


def test_hardlink_source_alias_reused_archive_alias_rejected(databases, tmp_path):
    alias = tmp_path / "safe-source-alias.duckdb"
    os.link(databases[0], alias)
    with cli._open_inputs((databases[0], str(alias), *databases[2:])) as handles:
        assert handles[0] is handles[1]
    with (
        pytest.raises(ValueError, match="SEPARATE_CURRENT_STRESS"),
        cli._open_inputs(
            (*databases[:6], str(alias)),
        ),
    ):
        raise AssertionError("Stress archive hardlink accepted")


def test_corrupt_seventh_file_closes_six_real_handles(databases, monkeypatch):
    Path(databases[-1]).write_bytes(b"synthetic corrupt stress archive")
    real = duckdb.connect
    opened: list[duckdb.DuckDBPyConnection] = []

    def connect(*args, **kwargs):
        assert kwargs == {"read_only": True}
        value = real(*args, **kwargs)
        opened.append(value)
        return value

    monkeypatch.setattr(duckdb, "connect", connect)
    with pytest.raises(duckdb.Error), cli._open_inputs(databases):
        raise AssertionError("Corrupt archive accepted")
    assert len(opened) == 6
    for conn in opened:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_body_exception_closes_all_handles(databases):
    with pytest.raises(RuntimeError, match="synthetic"), cli._open_inputs(databases) as handles:
        raise RuntimeError("synthetic")
    for conn in handles:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_review_keeps_partial_facts_but_no_nested_or_accepted_payload():
    value = negative(
        archived_recording_verified=True,
        current_source_checked=True,
        model_computation_rechecked=True,
        exact_recording_reproduced=True,
        archive_before="PRIVATE_RETAINED",
        fresh_before="PRIVATE_NATIVE",
    )
    raw, code = cli._summary(value, *PINS)
    result = json.loads(raw)
    assert code == 2 and result["exact_recording_reproduced"] is True
    assert result["archive_unchanged_observed"] is False
    assert result["accepted_study_metadata"] is None
    assert result["native_stress_fingerprint"] is None and result["evidence_fingerprint"] is None
    assert "PRIVATE_" not in raw and "fresh_before" not in result and "archive_before" not in result


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "unknown@2"},
        {"stress_record_id": "c" * 64},
        {"expected_recording_fingerprint": "c" * 64},
        {"current_source_checked": 1},
        {"publication_asserted": True},
        {"portfolio_pnl_asserted": True},
        {"reason_codes": ("private text",)},
        {"reason_codes": ("DUP", "DUP")},
        {"native_stress_fingerprint": "c" * 64},
        {"evidence_fingerprint": "c" * 64},
        {"study": "PRIVATE_STUDY"},
        {"status": "matched_current_research_iv_spot_stress_archive"},
        {"event_ts": "invented"},
        {"canonical_contract_id": "invented"},
        {"current_source_checked": True},
        {"model_computation_rechecked": True},
    ],
    ids=[
        "version",
        "record",
        "review",
        "bool",
        "publication",
        "pnl",
        "reason",
        "duplicate",
        "native-id",
        "evidence",
        "study",
        "incomplete",
        "clock",
        "identity",
        "facts",
        "model",
    ],
)
def test_invalid_or_escalated_summary_rejected(changes):
    with pytest.raises(ValueError):
        cli._summary(negative(**changes), *PINS)


def test_summary_limit_is_not_truncation(monkeypatch):
    monkeypatch.setattr(cli, "MAX_SUMMARY_BYTES", 1)
    with pytest.raises(ValueError, match="SUMMARY_BYTE_LIMIT"):
        cli._summary(negative(), *PINS)
