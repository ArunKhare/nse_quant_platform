"""No-I/O plans, negative projections and actual disposable DB boundaries; not native E2E."""

import builtins
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import research_iv_stress_attribution_cli as cli

PINS = ("a" * 64, "b" * 64)


def arguments(paths=None):
    chosen = paths or tuple("missing-" + str(i) for i in range(7))
    args: list[str] = []
    for name, path in zip(cli.PATH_NAMES, chosen, strict=True):
        args.extend(("--" + name, path))
    return args + ["--stress-record-id-pin", PINS[0], "--recording-fingerprint", PINS[1]]


def negative(**changes):
    values: dict[str, Any] = dict.fromkeys((*cli.OBSERVATION_FLAGS, *cli.DENIAL_FLAGS), False)
    values.update(dict.fromkeys((*cli.NULL_FIELDS, "attribution", "evidence_fingerprint")))
    values.update(
        version=cli.SERVICE_VERSION,
        stress_record_id=PINS[0],
        expected_recording_fingerprint=PINS[1],
        status="review_required",
        reason_codes=("SYNTHETIC_DIAGNOSTIC",),
    )
    values.update(changes)
    return SimpleNamespace(**values)


def test_plan_preserves_paths_without_io_or_native_imports(monkeypatch, capsys):
    real = builtins.__import__

    def guard(name, *args, **kwargs):
        if name == "duckdb" or name.startswith(
            (
                "scipy",
                "socket",
                "keyring",
                "nse_quant.data_platform.native_research_iv_stress_attribution",
                "nse_quant.data_platform.research_iv_stress_attribution",
                "nse_quant.data_platform.research_iv_stress_archive",
            )
        ):
            raise AssertionError("Plan imported execution code")
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
    assert value["plan"]["inputs_verified"] is False
    assert all(value["plan"][k] is False for k in cli.DENIAL_FLAGS)


@pytest.mark.parametrize(
    "field", ["--stress-record-id-pin", "--recording-fingerprint"], ids=["record", "fingerprint"]
)
@pytest.mark.parametrize(
    "bad", ["", "a" * 63, "A" * 64, "g" * 64], ids=["empty", "short", "uppercase", "hex"]
)
def test_review_pins_checked_before_paths(field, bad, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Bad pin reached path check")

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


@pytest.mark.parametrize(
    "flag",
    ["--shock-bps", "--baseline-delta", "--build-id-pin"],
    ids=["grid", "coefficients", "native-pin"],
)
def test_caller_replacement_inputs_not_supported(flag):
    with pytest.raises(SystemExit) as error:
        cli.main(arguments() + [flag, "0"])
    assert error.value.code == 2


def test_missing_execute_inputs_do_not_create_anything(tmp_path, capsys):
    paths = tuple(str(tmp_path / (str(i) + ".duckdb")) for i in range(7))
    assert cli.main(arguments(paths) + ["--execute"]) == 1
    assert list(tmp_path.iterdir()) == []
    assert json.loads(capsys.readouterr().out) == {
        "status": "FAILED",
        "reason_code": "IV_STRESS_ATTRIBUTION_INSPECTION_FAILED",
    }


def test_failure_message_sanitized(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise OSError("PRIVATE_EXCEPTION_BODY")

    monkeypatch.setattr(Path, "is_file", fail)
    assert cli.main(arguments() + ["--execute"]) == 1
    captured = capsys.readouterr()
    assert "PRIVATE_EXCEPTION_BODY" not in captured.out + captured.err


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


def test_seven_readonly_connections_and_normal_close(databases):
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


def test_supported_source_aliases_reuse_handle(databases):
    with cli._open_inputs((databases[0],) * 5 + databases[5:]) as handles:
        assert all(c is handles[0] for c in handles[:5])
        assert len({id(c) for c in handles}) == 3


ALIASES = [(role, prior) for role in (5, 6) for prior in range(role)]


@pytest.mark.parametrize(
    "pair", ALIASES, ids=[f"role{role}-prior{prior}" for role, prior in ALIASES]
)
def test_archive_role_aliases_rejected_before_connect(databases, monkeypatch, pair):
    role, prior = pair
    paths = list(databases)
    paths[role] = paths[prior]

    def forbidden(*args, **kwargs):
        raise AssertionError("Archive alias reached connect")

    monkeypatch.setattr(duckdb, "connect", forbidden)
    with pytest.raises(ValueError, match="SEPARATE_ATTRIBUTION"), cli._open_inputs(tuple(paths)):
        raise AssertionError("Archive alias accepted")


def test_hardlink_source_reuse_and_stress_archive_alias_rejection(databases, tmp_path):
    alias = tmp_path / "safe-hardlink.duckdb"
    os.link(databases[0], alias)
    with cli._open_inputs((databases[0], str(alias), *databases[2:])) as handles:
        assert handles[0] is handles[1]
    with (
        pytest.raises(ValueError, match="SEPARATE_ATTRIBUTION"),
        cli._open_inputs(
            (*databases[:6], str(alias)),
        ),
    ):
        raise AssertionError("Stress archive hardlink accepted")


def test_corrupt_last_file_closes_six_actual_handles(databases, monkeypatch):
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


def test_review_hides_provisional_attribution_and_full_context():
    value = negative(
        current_source_checked=True,
        model_computation_rechecked=True,
        provisional_attribution="PRIVATE_PROVISIONAL",
        before="PRIVATE_SOURCE",
    )
    raw, code = cli._summary(value, *PINS)
    result = json.loads(raw)
    assert code == 2 and result["accepted_attribution"] is None
    assert result["evidence_fingerprint"] is None
    assert result["model_computation_rechecked"] is True
    assert not result["approximation_accuracy_certified"]
    assert "PRIVATE_" not in raw and "before" not in result


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "unknown@2"},
        {"stress_record_id": "c" * 64},
        {"expected_recording_fingerprint": "c" * 64},
        {"current_source_checked": 1},
        {"approximation_accuracy_certified": True},
        {"portfolio_pnl_asserted": True},
        {"publication_asserted": True},
        {"reason_codes": ("private text",)},
        {"reason_codes": ("DUP", "DUP")},
        {"evidence_fingerprint": "c" * 64},
        {"attribution": "PRIVATE_ACCEPTED"},
        {"status": "computed_current_native_research_iv_stress_attribution"},
        {"event_ts": "invented"},
        {"canonical_contract_id": "invented"},
        {"model_computation_rechecked": True},
        {"attribution_reproduced": True},
    ],
    ids=[
        "version",
        "record",
        "review",
        "bool",
        "accuracy",
        "pnl",
        "publication",
        "reason",
        "duplicate",
        "evidence",
        "accepted",
        "incomplete",
        "time",
        "identity",
        "facts",
        "replay",
    ],
)
def test_escalated_or_inconsistent_summary_rejected(changes):
    with pytest.raises(ValueError):
        cli._summary(negative(**changes), *PINS)


def test_summary_limit_never_returns_truncated_output(monkeypatch):
    monkeypatch.setattr(cli, "MAX_SUMMARY_BYTES", 1)
    with pytest.raises(ValueError, match="SUMMARY_BYTE_LIMIT"):
        cli._summary(negative(), *PINS)
