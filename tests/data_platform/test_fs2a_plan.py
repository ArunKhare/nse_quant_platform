from nse_quant.data_platform.kite_silver_cli import main


def test_plan(tmp_path, capsys):
    assert (
        main(
            [
                "--bronze-db",
                str(tmp_path / "missing.duckdb"),
                "--silver-db",
                str(tmp_path / "silver.duckdb"),
                "--capture-event-id",
                "a" * 64,
                "--envelope-hash",
                "b" * 64,
                "--initialize",
            ]
        )
        == 0
    )
    assert not list(tmp_path.iterdir())
    assert '"inputs_verified": false' in capsys.readouterr().out
