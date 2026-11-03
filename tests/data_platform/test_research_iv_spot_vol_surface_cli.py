"""Plan/parser/negative diagnostics, actual min/max arithmetic and disposable DB I/O."""

import builtins
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import research_iv_spot_vol_surface_cli as cli

PINS = ("a" * 64, "b" * 64)


def arguments(paths=None):
    chosen = paths or tuple("missing-" + str(i) for i in range(7))
    args: list[str] = []
    for name, path in zip(cli.PATH_NAMES, chosen, strict=True):
        args.extend(("--" + name, path))
    return args + [
        "--stress-record-id-pin",
        PINS[0],
        "--recording-fingerprint",
        PINS[1],
        "--vol-shift-bps",
        "0",
    ]


def negative(**changes):
    values: dict[str, Any] = dict.fromkeys((*cli.OBSERVATION_FLAGS, *cli.DENIAL_FLAGS), False)
    values.update(dict.fromkeys((*cli.NULL_FIELDS, "surface", "evidence_fingerprint")))
    values.update(
        version=cli.SERVICE_VERSION,
        stress_record_id=PINS[0],
        expected_recording_fingerprint=PINS[1],
        vol_shifts_bps=(0,),
        hypothetical_volatility_shift_assumed=True,
        status="review_required",
        reason_codes=("SYNTHETIC_DIAGNOSTIC",),
    )
    values.update(changes)
    return SimpleNamespace(**values)


def test_plan_no_io_or_native_imports_and_no_derived_vol_check(monkeypatch, capsys):
    real = builtins.__import__

    def guard(name, *args, **kwargs):
        if name == "duckdb" or name.startswith(
            (
                "scipy",
                "socket",
                "keyring",
                "nse_quant.data_platform.native_research_iv_spot_vol_surface",
                "nse_quant.data_platform.research_iv_spot_vol_surface",
                "nse_quant.data_platform.research_iv_stress_archive",
            )
        ):
            raise AssertionError("Plan imported execution module")
        return real(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("Plan performed I/O")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", guard)
        patch.setattr(builtins, "open", forbidden)
        for method in ("open", "stat", "resolve", "exists", "is_file", "samefile"):
            patch.setattr(Path, method, forbidden)
        assert cli.main(arguments(("literal/../missing",) * 7)) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "PLANNED"
    assert all(p == "literal/../missing" for p in value["plan"]["paths_as_supplied"].values())
    assert value["plan"]["derived_coordinates_checked"] is False
    assert value["plan"]["inputs_verified"] is False
    assert value["plan"]["vol_shift_units"] == "ABSOLUTE_ANNUAL_SIGMA_BASIS_POINTS"


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
        ["0"] * 9,
    ],
    ids=[
        "empty",
        "negzero",
        "plus",
        "leading",
        "float",
        "space",
        "exponent",
        "low",
        "high",
        "duplicate",
        "order",
        "count",
    ],
)
def test_explicit_vol_shift_tokens_rejected_not_normalized(bad):
    with pytest.raises(ValueError):
        cli._vol_shifts(bad)


def test_signed_absolute_vol_shifts_parse_without_execution(capsys):
    args = arguments()[:-2] + [
        "--vol-shift-bps",
        "-5000",
        "--vol-shift-bps",
        "0",
        "--vol-shift-bps",
        "5000",
    ]
    assert cli.main(args) == 0
    assert json.loads(capsys.readouterr().out)["plan"]["vol_shifts_bps"] == [-5000, 0, 5000]


@pytest.mark.parametrize(
    "field", ["--stress-record-id-pin", "--recording-fingerprint"], ids=["record", "fingerprint"]
)
@pytest.mark.parametrize("bad", ["short", "A" * 64, "g" * 64], ids=["short", "uppercase", "hex"])
def test_pins_rejected_before_paths(field, bad, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Bad pin reached filesystem")

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


def test_cannot_replace_frozen_spot_grid():
    with pytest.raises(SystemExit) as error:
        cli.main(arguments() + ["--shock-bps", "0"])
    assert error.value.code == 2


def test_missing_inputs_not_created(tmp_path, capsys):
    paths = tuple(str(tmp_path / (str(i) + ".duckdb")) for i in range(7))
    assert cli.main(arguments(paths) + ["--execute"]) == 1
    assert list(tmp_path.iterdir()) == []
    assert json.loads(capsys.readouterr().out) == {
        "status": "FAILED",
        "reason_code": "IV_SPOT_VOL_SURFACE_INSPECTION_FAILED",
    }


def test_error_body_sanitized(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise OSError("PRIVATE_EXCEPTION")

    monkeypatch.setattr(Path, "is_file", fail)
    assert cli.main(arguments() + ["--execute"]) == 1
    captured = capsys.readouterr()
    assert "PRIVATE_EXCEPTION" not in captured.out + captured.err


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


def test_actual_readonly_handles_and_close(databases):
    with cli._open_inputs(databases) as handles:
        assert len(handles) == len({id(c) for c in handles}) == 7
        for conn in handles:
            row = conn.execute("SELECT current_database()").fetchone()
            assert row is not None
            catalog = '"' + str(row[0]).replace('"', '""') + '"'
            with pytest.raises(duckdb.Error):
                conn.execute(f'CREATE SCHEMA {catalog}."forbidden"')
    for conn in handles:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_supported_source_alias_reuse(databases):
    with cli._open_inputs((databases[0],) * 5 + databases[5:]) as handles:
        assert all(c is handles[0] for c in handles[:5])
        assert len({id(c) for c in handles}) == 3


ALIASES = [(role, prior) for role in (5, 6) for prior in range(role)]


@pytest.mark.parametrize(
    "pair", ALIASES, ids=[f"role{role}-prior{prior}" for role, prior in ALIASES]
)
def test_archives_distinct_before_open(databases, monkeypatch, pair):
    role, prior = pair
    paths = list(databases)
    paths[role] = paths[prior]

    def forbidden(*args, **kwargs):
        raise AssertionError("Archive alias reached connect")

    monkeypatch.setattr(duckdb, "connect", forbidden)
    with pytest.raises(ValueError, match="SEPARATE_SURFACE"), cli._open_inputs(tuple(paths)):
        raise AssertionError("Archive alias accepted")


def test_hardlink_source_reused_and_stress_alias_rejected(databases, tmp_path):
    alias = tmp_path / "safe-hardlink.duckdb"
    os.link(databases[0], alias)
    with cli._open_inputs((databases[0], str(alias), *databases[2:])) as handles:
        assert handles[0] is handles[1]
    with (
        pytest.raises(ValueError, match="SEPARATE_SURFACE"),
        cli._open_inputs(
            (*databases[:6], str(alias)),
        ),
    ):
        raise AssertionError("Stress archive alias accepted")


def test_corrupt_last_file_closes_six_open_handles(databases, monkeypatch):
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


def test_body_error_closes_handles(databases):
    with pytest.raises(RuntimeError, match="synthetic"), cli._open_inputs(databases) as handles:
        raise RuntimeError("synthetic")
    for conn in handles:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


def test_unrounded_metric_ranges_select_all_rows():
    rows = ((1.5, 0.25, -0.001), (-2.0, -0.5, 0.002), (0.0, 0.125, 0.0))
    result = cli._range_metrics(rows)
    assert result == dict(
        full_model_price_change_min=-2.0,
        full_model_price_change_max=1.5,
        interaction_change_min=-0.5,
        interaction_change_max=0.25,
        reconstruction_roundoff_abs_max=0.002,
    )


@pytest.mark.parametrize(
    "bad",
    [(), ((1.0, 2.0),), ((True, 0.0, 0.0),), ((float("nan"), 0.0, 0.0),), ((1.0, 2.0, 3.0),) * 17],
    ids=["empty", "shape", "bool", "nan", "count"],
)
def test_metric_input_never_accepts_prefix(bad):
    with pytest.raises(ValueError):
        cli._range_metrics(bad)


def test_review_omits_provisional_surface():
    value = negative(
        current_source_checked=True,
        model_computation_rechecked=True,
        provisional_surface="PRIVATE_PROVISIONAL",
        before="PRIVATE_CONTEXT",
    )
    raw, code = cli._summary(value, *PINS, (0,))
    result = json.loads(raw)
    assert code == 2 and result["accepted_surface_summary"] is None
    assert result["evidence_fingerprint"] is None
    assert "PRIVATE_" not in raw and "provisional_surface" not in result


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "unknown@2"},
        {"stress_record_id": "c" * 64},
        {"expected_recording_fingerprint": "c" * 64},
        {"vol_shifts_bps": (1,)},
        {"hypothetical_volatility_shift_assumed": 1},
        {"volatility_response_modelled": True},
        {"portfolio_pnl_asserted": True},
        {"publication_asserted": True},
        {"current_source_checked": 1},
        {"reason_codes": ("private text",)},
        {"reason_codes": ("DUP", "DUP")},
        {"surface": "PRIVATE_ACCEPTED"},
        {"evidence_fingerprint": "c" * 64},
        {"status": "computed_current_native_research_iv_spot_vol_surface"},
        {"event_ts": "invented"},
        {"model_computation_rechecked": True},
        {"surface_reproduced": True},
    ],
    ids=[
        "version",
        "record",
        "review",
        "grid",
        "assumption",
        "forecast",
        "pnl",
        "publication",
        "bool",
        "reason",
        "duplicate",
        "surface",
        "evidence",
        "incomplete",
        "clock",
        "facts",
        "repeat",
    ],
)
def test_escalation_or_invalid_diagnostic_rejected(changes):
    with pytest.raises(ValueError):
        cli._summary(negative(**changes), *PINS, (0,))


def test_summary_bound_is_not_truncation(monkeypatch):
    monkeypatch.setattr(cli, "MAX_SUMMARY_BYTES", 1)
    with pytest.raises(ValueError, match="SUMMARY_BYTE_LIMIT"):
        cli._summary(negative(), *PINS, (0,))
