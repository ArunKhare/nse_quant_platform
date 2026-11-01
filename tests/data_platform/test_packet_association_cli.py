"""Plan-first boundary tests for association persistence CLI."""

import builtins
import json

import pytest

from nse_quant.data_platform.packet_association_cli import main


def arguments(tmp_path):
    return [
        "--bronze-db",
        str(tmp_path / "bronze.duckdb"),
        "--frame-silver-db",
        str(tmp_path / "frames.duckdb"),
        "--reference-silver-db",
        str(tmp_path / "reference.duckdb"),
        "--assessment-db",
        str(tmp_path / "assessments.duckdb"),
        "--frame-revision-id",
        "a" * 64,
        "--reference-assessment-revision-id",
        "b" * 64,
        "--packet-ordinal",
        "0",
    ]


def test_plan_no_execution_imports_or_files(tmp_path, monkeypatch, capsys):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"duckdb", "nse_quant.data_platform.packet_association_silver"}:
            raise AssertionError("Plan imported execution dependency")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert main(arguments(tmp_path) + ["--initialize"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PLANNED"
    assert output["plan"]["inputs_verified"] is False
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("ordinal", ["-1", "4096", "abc"])
def test_bad_ordinal(tmp_path, ordinal):
    args = arguments(tmp_path)
    args[-1] = ordinal
    with pytest.raises(SystemExit):
        main(args)


def test_execution_requires_identity_and_existing_inputs(tmp_path):
    with pytest.raises(SystemExit):
        main(arguments(tmp_path) + ["--execute", "--initialize"])
    assert list(tmp_path.iterdir()) == []


def test_target_cannot_be_input_even_in_plan(tmp_path):
    args = arguments(tmp_path)
    args[7] = args[1]
    with pytest.raises(SystemExit):
        main(args)
