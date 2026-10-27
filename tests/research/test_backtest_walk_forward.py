from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from nse_quant.research.backtest.config import BacktestConfig
from nse_quant.research.backtest.experiments import ParameterGrid
from nse_quant.research.backtest.walk_forward import (
    build_snapshot_folds,
    group_snapshots_by_date,
    run_walk_forward_experiments,
    save_walk_forward_results,
)


class StubSnapshot:
    def __init__(self, day: date) -> None:
        self.ts = datetime(day.year, day.month, day.day, 4, 15, tzinfo=UTC)


class StubEngine:
    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self.portfolio = type(
            "Portfolio",
            (),
            {
                "closed_trades": [
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
                ],
            },
        )()

    def prepare_replay(self, snapshots: list) -> list:
        return [{"snapshot": snapshot} for snapshot in snapshots]

    def run(self, snapshots=None, prepared_steps=None):
        start = datetime(2026, 10, 21, 4, 15, tzinfo=UTC)

        return type(
            "Result",
            (),
            {
                "decisions": [{}, {}],
                "proposal_count": 1,
                "equity_curve": [
                    {"ts": start, "equity": 1_000_000.0},
                    {
                        "ts": start + timedelta(minutes=1),
                        "equity": 1_000_100.0,
                    },
                ],
            },
        )()

    def save(self, result):
        output_dir = self.config.output_dir / self.config.run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir


def test_build_date_folds_is_no_lookahead():
    folds = build_snapshot_folds(
        snapshot_dates=[
            date(2026, 10, 21),
            date(2026, 10, 23),
            date(2026, 10, 27),
        ],
        train_days=2,
        test_days=1,
    )

    assert len(folds) == 1

    fold = folds[0]
    assert fold.train_dates == [date(2026, 10, 21), date(2026, 10, 23)]
    assert fold.test_dates == [date(2026, 10, 27)]


def test_group_snapshots_by_date():
    snapshots = [
        StubSnapshot(date(2026, 10, 21)),
        StubSnapshot(date(2026, 10, 21)),
        StubSnapshot(date(2026, 10, 23)),
    ]

    grouped = group_snapshots_by_date(snapshots)

    assert len(grouped[date(2026, 10, 21)]) == 2
    assert len(grouped[date(2026, 10, 23)]) == 1


def test_walk_forward_marks_insufficient_train_trades(tmp_path):
    base_config = BacktestConfig(
        warehouse_dir=tmp_path / "warehouse",
        output_dir=tmp_path / "backtests",
        start_date=date(2026, 10, 21),
        end_date=date(2026, 10, 27),
        run_id="walk_forward",
    )

    snapshots = [
        StubSnapshot(date(2026, 10, 21)),
        StubSnapshot(date(2026, 10, 23)),
        StubSnapshot(date(2026, 10, 27)),
    ]

    results = run_walk_forward_experiments(
        base_config=base_config,
        grid=ParameterGrid(),
        engine_factory=StubEngine,
        snapshot_loader=lambda: snapshots,
        train_days=2,
        test_days=1,
        min_train_trades=10,
    )

    assert len(results) == 1
    assert results[0].selection_status == "INSUFFICIENT_TRAIN_TRADES"
    assert results[0].selected_parameters is None
    assert results[0].test_result is None


def test_save_walk_forward_results(tmp_path):
    base_config = BacktestConfig(
        warehouse_dir=tmp_path / "warehouse",
        output_dir=tmp_path / "backtests",
        start_date=date(2026, 10, 21),
        end_date=date(2026, 10, 27),
        run_id="walk_forward",
    )

    snapshots = [
        StubSnapshot(date(2026, 10, 21)),
        StubSnapshot(date(2026, 10, 23)),
        StubSnapshot(date(2026, 10, 27)),
    ]

    results = run_walk_forward_experiments(
        base_config=base_config,
        grid=ParameterGrid(),
        engine_factory=StubEngine,
        snapshot_loader=lambda: snapshots,
        train_days=2,
        test_days=1,
        min_train_trades=10,
    )

    results_path, summary_path = save_walk_forward_results(
        results=results,
        output_dir=tmp_path / "walk_forward",
    )

    assert results_path.exists()
    assert summary_path.exists()
