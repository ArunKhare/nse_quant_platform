"""Planning must not import DuckDB or open input/output files."""

import builtins

from nse_quant.data_platform import s2_iv30_feature_cli as cli


def test_cli_plan_does_no_io(tmp_path, monkeypatch, capsys):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "duckdb" or name == "nse_quant.data_platform":
            raise AssertionError("Feature planning imported execution dependencies")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert (
        cli.main(
            [
                "eod",
                "--series-db",
                str(tmp_path / "missing.duckdb"),
                "--observation-id",
                "a" * 64,
                "--expected-sha256",
                "b" * 64,
                "--as-of",
                "2026-11-25T10:00:00+00:00",
                "--output",
                str(tmp_path / "feature.json"),
            ]
        )
        == 0
    )
    assert not list(tmp_path.iterdir())
    assert "PLANNED_NO_IO" in capsys.readouterr().out
