"""Read-only publication inspection plan and actual registry reads."""

import builtins
import json

import pytest

from nse_quant.data_platform import quote_publication_inspect_cli as cli


def arguments(tmp_path):
    return ["--publication-db", str(tmp_path / "registry.duckdb"), "--publication-id", "a" * 64]


def test_default_plan_no_execution_imports_or_creation(tmp_path, monkeypatch, capsys):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"duckdb", "nse_quant.data_platform.quote_publication_reader"}:
            raise AssertionError("Plan imported execution")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert cli.main(arguments(tmp_path)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PLANNED"
    assert not result["source_current_checked"]
    assert not result["decision_eligibility_asserted"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("flag", ["--execute", "--as-of", "--repair", "--initialize"])
def test_no_write_or_time_travel_switch(tmp_path, flag):
    with pytest.raises(SystemExit):
        cli.main(arguments(tmp_path) + [flag])


def test_missing_registry_never_created(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(arguments(tmp_path) + ["--inspect"])
    assert list(tmp_path.iterdir()) == []
