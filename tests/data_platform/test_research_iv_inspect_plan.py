"""Plan-only CLI checks; no reconstructed native dependencies or DB harness."""

import builtins
import json
from pathlib import Path

from nse_quant.data_platform.research_iv_inspect_cli import main


def test_default_plan_has_no_io_or_execution_import(monkeypatch, capsys):
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"duckdb", "nse_quant.data_platform.research_iv_revalidation"}:
            raise AssertionError("Plan imported execution dependency")
        return real_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("Plan probed/opened a path")

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(builtins, "open", forbidden)
    for method in ("open", "resolve", "exists", "is_file", "stat", "samefile"):
        monkeypatch.setattr(Path, method, forbidden)
    result = main(
        [
            "--bronze-db",
            "missing-bronze.duckdb",
            "--frame-silver-db",
            "missing-frame.duckdb",
            "--reference-silver-db",
            "missing-reference.duckdb",
            "--assessment-db",
            "missing-audit.duckdb",
            "--source-gold-db",
            "missing-source-gold.duckdb",
            "--archive-db",
            "missing-archive.duckdb",
            "--build-id-pin",
            "a" * 64,
            "--archive-fingerprint",
            "b" * 64,
        ]
    )
    assert result == 0
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "PLANNED"
    assert value["plan"]["inputs_verified"] is False
    assert value["plan"]["current_source_checked"] is False
    assert value["plan"]["publication_requested"] is False
