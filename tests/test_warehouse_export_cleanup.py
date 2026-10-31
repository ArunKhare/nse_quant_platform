"""Regression tests for export consolidation and compatibility entry points."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nse_quant.persistence import warehouse_exports as exports

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "prefix,builder",
    [
        ("option_stream", exports.build_option_stream_export_path),
        ("market_regime", exports.build_regime_export_path),
    ],
)
def test_partition_paths(tmp_path, prefix, builder):
    assert builder(export_dir=tmp_path, underlying="NIFTY", trading_date=date(2026, 10, 30)) == (
        tmp_path / "underlying=NIFTY/year=2026/month=10" / f"{prefix}_2026-10-30.parquet"
    )


def test_option_empty_does_not_copy(tmp_path):
    store = MagicMock()
    store.conn.execute.return_value.fetchone.return_value = (0,)
    assert (
        exports.export_option_stream(
            store=store,
            export_dir=tmp_path,
            underlying="NIFTY",
            trading_date=date(2026, 10, 30),
        )
        == 1
    )
    assert store.conn.execute.call_count == 1
    store.conn.close.assert_not_called()


def test_option_copy_preserves_schema_parameters_and_escaping(tmp_path):
    store = MagicMock()
    store.conn.execute.return_value.fetchone.return_value = (3,)
    day = date(2026, 10, 30)
    assert (
        exports.export_option_stream(
            store=store,
            export_dir=tmp_path / "user's",
            underlying="NIFTY",
            trading_date=day,
        )
        == 0
    )
    sql, parameters = store.conn.execute.call_args.args
    expected = expected = [
        "run_id",
        "ts",
        "underlying",
        "expiry",
        "strike",
        "option_type",
        "tradingsymbol",
        "instrument_token",
        "lot_size",
        "spot",
        "ltp",
        "bid",
        "ask",
        "volume",
        "oi",
        "iv",
        "delta",
        "gamma",
        "vega",
        "theta",
        "quote_status",
        "payload_json",
    ]
    selection = sql.split("SELECT", 1)[1].split("FROM", 1)[0]
    assert [column.strip() for column in selection.split(",")] == expected
    assert parameters == ["NIFTY", day]
    assert "user''s" in sql
    assert "ORDER BY ts" in sql
    assert "COMPRESSION ZSTD" in sql


def test_regime_export_delegates_and_preserves_empty_success(tmp_path):
    store = MagicMock()
    day = date(2026, 10, 30)
    store.conn.execute.return_value.fetchall.return_value = [(day,)]
    assert (
        exports.export_market_regimes(
            store=store,
            export_dir=tmp_path,
            underlying="NIFTY",
            start_date=day,
            end_date=day,
        )
        == 0
    )
    store.export_market_regime_parquet.assert_called_once_with(
        output_path=exports.build_regime_export_path(
            export_dir=tmp_path,
            underlying="NIFTY",
            trading_date=day,
        ),
        underlying="NIFTY",
        date_str="2026-10-30",
    )
    store.conn.execute.return_value.fetchall.return_value = []
    assert (
        exports.export_market_regimes(
            store=store,
            export_dir=tmp_path,
            underlying="NIFTY",
            start_date=day,
            end_date=day,
        )
        == 0
    )


def test_cli_defaults_and_symbol_alias():
    cli = load_script("export_warehouse")
    args = cli.parse_args(["option-stream", "--date", "2026-10-30"])
    assert args.underlying == "NIFTY"
    assert args.export_dir == Path("data/exports")
    args = cli.parse_args(
        [
            "market-regimes",
            "--symbol",
            "BANKNIFTY",
            "--start-date",
            "2026-10-29",
            "--end-date",
            "2026-10-30",
        ]
    )
    assert args.underlying == "BANKNIFTY"


def test_cli_rejects_reversed_range_before_opening_store(monkeypatch):
    cli = load_script("export_warehouse")
    factory = MagicMock()
    monkeypatch.setattr(cli, "DuckDBStore", factory)
    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "market-regimes",
                "--start-date",
                "2026-10-30",
                "--end-date",
                "2026-10-29",
            ]
        )
    assert error.value.code == 2
    factory.assert_not_called()


@pytest.mark.parametrize(
    "script,argv,function",
    [
        ("export_warehouse", ["option-stream", "--date", "2026-10-30"], "export_option_stream"),
        ("backfill_option_stream_exports", ["--date", "2026-10-30"], "export_option_stream"),
        (
            "backfill_market_regime_exports",
            [
                "--start-date",
                "2026-10-29",
                "--end-date",
                "2026-10-30",
            ],
            "export_market_regimes",
        ),
    ],
)
def test_entrypoints_forward_custom_directory_close_and_propagate(
    monkeypatch, tmp_path, script, argv, function
):
    cli = load_script(script)
    store = MagicMock()
    monkeypatch.setattr(cli, "DuckDBStore", lambda: store)
    operation = MagicMock(return_value=1)
    monkeypatch.setattr(cli, function, operation)
    arguments = [*argv, "--export-dir", str(tmp_path)]
    assert cli.main(arguments) == 1
    assert operation.call_args.kwargs["export_dir"] == tmp_path
    store.conn.close.assert_called_once()
    store.conn.close.reset_mock()
    operation.side_effect = RuntimeError("export failed")
    with pytest.raises(RuntimeError, match="export failed"):
        cli.main(arguments)
    store.conn.close.assert_called_once()
