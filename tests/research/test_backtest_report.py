from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from nse_quant.research.backtest.report import (
    calculate_performance_summary,
    equity_to_returns,
    generate_backtest_report,
    load_equity_curve,
    load_trade_performance,
)


def write_backtest_outputs(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)

    start = datetime(2026, 10, 26, 4, 15, tzinfo=UTC)
    equity_values = [1_000_000.0, 1_010_000.0, 1_005_000.0, 1_020_000.0]

    equity_frame = pd.DataFrame(
        {
            "ts": [start + timedelta(minutes=minute) for minute in range(4)],
            "equity": equity_values,
            "open_positions": [0, 1, 1, 0],
        },
    )
    equity_frame.to_csv(run_dir / "equity_curve.csv", index=False)

    trades_frame = pd.DataFrame(
        {
            "realized_pnl": [10_000.0, -5_000.0, 15_000.0],
        },
    )
    trades_frame.to_csv(run_dir / "trades.csv", index=False)


def test_load_equity_curve_and_returns(tmp_path):
    run_dir = tmp_path / "run"
    write_backtest_outputs(run_dir)

    equity = load_equity_curve(run_dir / "equity_curve.csv")
    returns = equity_to_returns(equity)

    assert len(equity) == 4
    assert len(returns) == 3
    assert returns.iloc[0] == pytest.approx(0.01)


def test_trade_performance_counts_wins_and_profit_factor(tmp_path):
    run_dir = tmp_path / "run"
    write_backtest_outputs(run_dir)

    performance = load_trade_performance(run_dir / "trades.csv")

    assert performance["trade_count"] == 3
    assert performance["win_rate"] == pytest.approx(2 / 3)
    assert performance["profit_factor"] == pytest.approx(25_000.0 / 5_000.0)


def test_performance_summary_contains_required_metrics(tmp_path):
    run_dir = tmp_path / "run"
    write_backtest_outputs(run_dir)

    equity = load_equity_curve(run_dir / "equity_curve.csv")
    returns = equity_to_returns(equity)
    trade_performance = load_trade_performance(run_dir / "trades.csv")

    summary = calculate_performance_summary(
        equity=equity,
        returns=returns,
        trade_performance=trade_performance,
    )

    required = {
        "total_return",
        "cagr",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown",
        "volatility",
        "trade_count",
        "win_rate",
        "profit_factor",
    }

    assert required.issubset(summary)
    assert summary["total_return"] == pytest.approx(0.02)
    assert summary["cagr"] is None
    assert summary["trade_count"] == 3


def test_generate_backtest_report_writes_outputs(tmp_path):
    run_dir = tmp_path / "run"
    write_backtest_outputs(run_dir)

    report_path, summary_path = generate_backtest_report(run_dir)

    assert report_path.exists()
    assert report_path.name == "quantstats_report.html"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["run_id"] == "run"
    assert summary["equity_points"] == 4
    assert summary["initial_equity"] == 1_000_000.0
    assert summary["final_equity"] == 1_020_000.0
    assert summary["total_return"] == pytest.approx(0.02)
    assert summary["cagr"] is None
