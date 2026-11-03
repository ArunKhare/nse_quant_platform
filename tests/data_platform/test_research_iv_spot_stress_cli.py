"""Plan/parser/negative diagnostics and actual synthetic read-only DB I/O; not native E2E."""

import builtins
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import research_iv_spot_stress_cli as cli

PINS = ("a" * 64, "b" * 64, "c" * 64)


def arguments(paths=None):
    chosen = paths or tuple("missing-" + str(i) for i in range(6))
    result: list[str] = []
    for name, path in zip(cli.PATH_NAMES, chosen, strict=True):
        result.extend(("--" + name, path))
    return result + [
        "--build-id-pin",
        PINS[0],
        "--archive-fingerprint",
        PINS[1],
        "--revalidation-fingerprint",
        PINS[2],
        "--shock-bps",
        "0",
    ]


def negative(**changes):
    value: dict[str, Any] = dict.fromkeys((*cli.OBSERVATION_FLAGS, *cli.DENIAL_FLAGS), False)
    value.update(dict.fromkeys(cli.NULL_FIELDS))
    value.update(
        version=cli.SERVICE_VERSION,
        build_id=PINS[0],
        expected_archive_fingerprint=PINS[1],
        expected_revalidation_fingerprint=PINS[2],
        status="review_required",
        reason_codes=("SYNTHETIC_DIAGNOSTIC",),
        study=None,
        evidence_fingerprint=None,
    )
    value.update(changes)
    return SimpleNamespace(**value)


def test_plan_no_io_execution_imports_or_path_normalization(monkeypatch, capsys):
    real = builtins.__import__

    def guard(name, *args, **kwargs):
        if name == "duckdb" or name.startswith(
            (
                "scipy",
                "socket",
                "keyring",
                "nse_quant.data_platform.native_research_iv_spot_stress",
                "nse_quant.data_platform.research_iv_spot_stress",
                "nse_quant.data_platform.research_option_model",
            )
        ):
            raise AssertionError("Plan imported execution module")
        return real(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("Plan probed/opened a path")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", guard)
        patch.setattr(builtins, "open", forbidden)
        for name in ("resolve", "open", "exists", "stat", "is_file", "samefile"):
            patch.setattr(Path, name, forbidden)
        assert cli.main(arguments(("literal/../missing",) * 6)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PLANNED"
    assert all(v == "literal/../missing" for v in result["plan"]["paths_as_supplied"].values())
    assert not result["plan"]["inputs_verified"] and not result["plan"]["current_source_checked"]


@pytest.mark.parametrize(
    "bad",
    [
        [],
        ["-0"],
        ["+1"],
        ["01"],
        ["1.0"],
        [" 1"],
        ["1e2"],
        ["-5001"],
        ["5001"],
        ["0", "0"],
        ["1", "0"],
        ["0"] * 17,
    ],
    ids=[
        "empty",
        "negzero",
        "plus",
        "leading",
        "float",
        "space",
        "exp",
        "low",
        "high",
        "duplicate",
        "unsorted",
        "count",
    ],
)
def test_shock_literal_contract(bad):
    with pytest.raises(ValueError):
        cli._shocks(bad)


def test_exact_sorted_shocks_and_inclusive_bounds():
    assert cli._shocks(["-5000", "-1", "0", "1", "5000"]) == (-5000, -1, 0, 1, 5000)


@pytest.mark.parametrize(
    "field",
    ["--build-id-pin", "--archive-fingerprint", "--revalidation-fingerprint"],
    ids=["build", "archive", "native"],
)
@pytest.mark.parametrize("bad", ["short", "A" * 64, "g" * 64], ids=["short", "upper", "hex"])
def test_pins_rejected_before_path_checks(field, bad, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Bad pin reached filesystem")

    monkeypatch.setattr(Path, "is_file", forbidden)
    args = arguments() + ["--execute"]
    args[args.index(field) + 1] = bad
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2


@pytest.mark.parametrize("bad", ["", "x" * 4097, "private\npath"], ids=["empty", "long", "control"])
def test_path_literal_bounds(bad):
    args = arguments()
    args[1] = bad
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2


def test_missing_execute_does_not_create_anything(tmp_path, capsys):
    paths = tuple(str(tmp_path / (str(i) + ".duckdb")) for i in range(6))
    assert cli.main(arguments(paths) + ["--execute"]) == 1
    assert list(tmp_path.iterdir()) == []
    assert json.loads(capsys.readouterr().out) == {
        "status": "FAILED",
        "reason_code": "IV_SPOT_STRESS_INSPECTION_FAILED",
    }


def test_error_sanitized(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise OSError("PRIVATE_EXCEPTION")

    monkeypatch.setattr(Path, "is_file", fail)
    assert cli.main(arguments() + ["--execute"]) == 1
    captured = capsys.readouterr()
    assert "PRIVATE_EXCEPTION" not in captured.out + captured.err


@pytest.fixture
def databases(tmp_path):
    paths = tuple(tmp_path / (str(i) + ".duckdb") for i in range(6))
    for path in paths:
        with duckdb.connect(str(path)) as conn:
            row = conn.execute("SELECT current_database()").fetchone()
            assert row is not None
            catalog = '"' + str(row[0]).replace('"', '""') + '"'
            conn.execute(f'CREATE TABLE {catalog}."main"."synthetic" (v INTEGER)')
    return tuple(map(str, paths))


def test_actual_readonly_handles_and_close(databases):
    with cli._open_inputs(databases) as handles:
        assert len(handles) == len({id(c) for c in handles}) == 6
        for conn in handles:
            row = conn.execute("SELECT current_database()").fetchone()
            assert row is not None
            catalog = '"' + str(row[0]).replace('"', '""') + '"'
            with pytest.raises(duckdb.Error):
                conn.execute(f'CREATE SCHEMA {catalog}."forbidden"')
    for conn in handles:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_supported_source_aliases_reuse_one_handle(databases):
    with cli._open_inputs((databases[0],) * 5 + databases[5:]) as handles:
        assert all(c is handles[0] for c in handles[:5])
        assert handles[5] is not handles[0]


@pytest.mark.parametrize(
    "role", range(5), ids=["bronze", "frame", "reference", "assessment", "gold"]
)
def test_archive_aliases_rejected_before_open(databases, monkeypatch, role):
    paths = (*databases[:5], databases[role])

    def forbidden(*args, **kwargs):
        raise AssertionError("Archive alias reached connect")

    monkeypatch.setattr(duckdb, "connect", forbidden)
    with pytest.raises(ValueError, match="SEPARATE_STRESS_ARCHIVE"), cli._open_inputs(paths):
        raise AssertionError("Alias accepted")


def test_hardlink_source_reused_and_archive_hardlink_rejected(databases, tmp_path):
    link = tmp_path / "safe-alias.duckdb"
    os.link(databases[0], link)
    with cli._open_inputs((databases[0], str(link), *databases[2:])) as handles:
        assert handles[0] is handles[1]
    with (
        pytest.raises(ValueError, match="SEPARATE_STRESS_ARCHIVE"),
        cli._open_inputs(
            (*databases[:5], str(link)),
        ),
    ):
        raise AssertionError("Archive hardlink accepted")


def test_corrupt_later_database_closes_all_opened_handles(databases, monkeypatch):
    Path(databases[-1]).write_bytes(b"synthetic corrupt archive")
    real = duckdb.connect
    opened: list[duckdb.DuckDBPyConnection] = []

    def connect(*args, **kwargs):
        assert kwargs == {"read_only": True}
        value = real(*args, **kwargs)
        opened.append(value)
        return value

    monkeypatch.setattr(duckdb, "connect", connect)
    with pytest.raises(duckdb.Error), cli._open_inputs(databases):
        raise AssertionError("Corrupt file accepted")
    assert len(opened) == 5
    for conn in opened:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_review_projection_omits_provisional_curves():
    value = negative(current_source_checked=True, provisional_study="PRIVATE_PROVISIONAL")
    raw, code = cli._summary(value, PINS, (0,))
    result = json.loads(raw)
    assert code == 2 and result["accepted_study"] is None
    assert result["current_source_checked"] is True
    assert "PRIVATE_PROVISIONAL" not in raw and "provisional_study" not in result


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "unknown@2"},
        {"build_id": "d" * 64},
        {"expected_archive_fingerprint": "d" * 64},
        {"expected_revalidation_fingerprint": "d" * 64},
        {"publication_asserted": True},
        {"portfolio_pnl_asserted": True},
        {"current_source_checked": 1},
        {"reason_codes": ("private text",)},
        {"reason_codes": ("DUP", "DUP")},
        {"evidence_fingerprint": "d" * 64},
        {"study": "PRIVATE_ACCEPTED"},
        {"status": "computed_current_native_research_iv_spot_stress"},
        {"event_ts": "invented"},
    ],
    ids=[
        "version",
        "build",
        "archive",
        "native",
        "authority",
        "pnl",
        "bool",
        "reason",
        "duplicate",
        "evidence",
        "study",
        "incomplete",
        "clock",
    ],
)
def test_invalid_or_escalated_diagnostics_reject(changes):
    with pytest.raises(ValueError):
        cli._summary(negative(**changes), PINS, (0,))


def test_summary_bound_is_not_truncation(monkeypatch):
    monkeypatch.setattr(cli, "MAX_SUMMARY_BYTES", 1)
    with pytest.raises(ValueError, match="SUMMARY_BYTE_LIMIT"):
        cli._summary(negative(), PINS, (0,))


def test_body_failure_closes_all_actual_handles(databases):
    with pytest.raises(RuntimeError, match="synthetic"), cli._open_inputs(databases) as handles:
        raise RuntimeError("synthetic")
    for conn in handles:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_negative_shocks_parse_as_values_without_execution(capsys):
    args = arguments()[:-2] + ["--shock-bps", "-5000", "--shock-bps", "0", "--shock-bps", "5000"]
    assert cli.main(args) == 0
    assert json.loads(capsys.readouterr().out)["plan"]["shocks_bps"] == [-5000, 0, 5000]
