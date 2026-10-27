from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from nse_quant.research.backtest.config import BacktestConfig
from nse_quant.research.backtest.experiments import (
    ParameterGrid,
    calculate_max_drawdown,
    run_parameter_experiments,
    save_experiment_results,
)


def stub_snapshot_loader():
    return [object(), object()]


class StubEngine:
    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self.received_snapshots: list | None = None
        self.portfolio = type(
            "Portfolio",
            (),
            {
                "closed_trades": [
                    type("Trade", (), {"realized_pnl": 100.0})(),
                    type("Trade", (), {"realized_pnl": -40.0})(),
                ],
            },
        )()

    def run(self, snapshots=None):
        start = datetime(2026, 10, 26, 4, 15, tzinfo=UTC)
        self.received_snapshots = snapshots

        return type(
            "Result",
            (),
            {
                "decisions": [{}, {}, {}],
                "proposal_count": 2,
                "equity_curve": [
                    {"ts": start, "equity": 1_000_000.0},
                    {
                        "ts": start + timedelta(minutes=1),
                        "equity": 1_010_000.0,
                    },
                    {
                        "ts": start + timedelta(minutes=2),
                        "equity": 1_006_000.0,
                    },
                ],
            },
        )()

    def save(self, result):
        output_dir = self.config.output_dir / self.config.run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir


def test_parameter_grid_creates_cartesian_product():
    grid = ParameterGrid(
        iv_collapse_pct=(15.0, 20.0),
        expected_move_buffer=(1.0, 1.25),
        entry_cooldown_minutes=(15,),
    )

    combinations = grid.combinations()

    assert len(combinations) == 4
    assert {
        "iv_collapse_pct": 15.0,
        "expected_move_buffer": 1.0,
        "entry_cooldown_minutes": 15,
    } in combinations


def test_max_drawdown_uses_running_peak():
    equity = pd.Series([100.0, 120.0, 90.0, 110.0])

    assert calculate_max_drawdown(equity) == pytest.approx(-0.25)


def test_run_parameter_experiments_creates_isolated_runs(tmp_path):
    base_config = BacktestConfig(
        warehouse_dir=tmp_path / "warehouse",
        output_dir=tmp_path / "backtests",
        start_date=date(2026, 10, 21),
        end_date=date(2026, 10, 23),
        run_id="experiment",
    )

    grid = ParameterGrid(
        iv_collapse_pct=(15.0, 20.0),
        expected_move_buffer=(1.25,),
        entry_cooldown_minutes=(15,),
    )

    results = run_parameter_experiments(
        base_config=base_config,
        grid=grid,
        engine_factory=StubEngine,
        snapshot_loader=stub_snapshot_loader,
    )

    assert len(results) == 2
    assert results[0].run_id == "experiment_exp000"
    assert results[1].run_id == "experiment_exp001"
    assert results[0].trade_count == 2
    assert results[0].win_rate == pytest.approx(0.5)
    assert results[0].profit_factor == pytest.approx(2.5)
    assert results[0].total_return == pytest.approx(0.006)
    assert results[0].snapshot_count == 3


def test_save_experiment_results_writes_outputs(tmp_path):
    base_config = BacktestConfig(
        warehouse_dir=tmp_path / "warehouse",
        output_dir=tmp_path / "backtests",
        start_date=date(2026, 10, 21),
        end_date=date(2026, 10, 23),
        run_id="experiment",
    )

    results = run_parameter_experiments(
        base_config=base_config,
        grid=ParameterGrid(),
        engine_factory=StubEngine,
        snapshot_loader=stub_snapshot_loader,
    )

    results_path, summary_path = save_experiment_results(
        results=results,
        output_dir=tmp_path / "experiments",
    )

    assert results_path.exists()
    assert summary_path.exists()

    summary = summary_path.read_text(encoding="utf-8")
    assert "INSUFFICIENT_DATA_FOR_OPTIMIZATION" in summary


def test_experiment_result_records_exit_reason_counts(tmp_path):
    base_config = BacktestConfig(
        warehouse_dir=tmp_path / "warehouse",
        output_dir=tmp_path / "backtests",
        start_date=date(2026, 10, 21),
        end_date=date(2026, 10, 23),
        run_id="reasons",
    )

    class ReasonEngine(StubEngine):
        def __init__(self, config: BacktestConfig) -> None:
            super().__init__(config)

            self.portfolio.closed_trades = [
                type(
                    "Trade",
                    (),
                    {
                        "realized_pnl": 100.0,
                        "exit_reason": type(
                            "Reason",
                            (),
                            {"value": "TARGET_PROFIT"},
                        )(),
                    },
                )(),
                type(
                    "Trade",
                    (),
                    {
                        "realized_pnl": -40.0,
                        "exit_reason": type(
                            "Reason",
                            (),
                            {"value": "STOP_LOSS"},
                        )(),
                    },
                )(),
            ]

    results = run_parameter_experiments(
        base_config=base_config,
        grid=ParameterGrid(),
        engine_factory=ReasonEngine,
        snapshot_loader=stub_snapshot_loader,
    )

    assert results[0].exit_reason_counts == {
        "TARGET_PROFIT": 1,
        "STOP_LOSS": 1,
    }
