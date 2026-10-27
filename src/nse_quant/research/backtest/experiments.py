from __future__ import annotations

import itertools
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from nse_quant.research.backtest.config import BacktestConfig
from nse_quant.research.backtest.engine import BacktestEngine


@dataclass(frozen=True)
class ParameterGrid:
    iv_collapse_pct: tuple[float, ...] = (20.0,)
    expected_move_buffer: tuple[float, ...] = (1.25,)
    entry_cooldown_minutes: tuple[int, ...] = (15,)

    def combinations(self) -> list[dict[str, float | int]]:
        return [
            {
                "iv_collapse_pct": iv_collapse_pct,
                "expected_move_buffer": expected_move_buffer,
                "entry_cooldown_minutes": entry_cooldown_minutes,
            }
            for iv_collapse_pct, expected_move_buffer, entry_cooldown_minutes in itertools.product(
                self.iv_collapse_pct,
                self.expected_move_buffer,
                self.entry_cooldown_minutes,
            )
        ]


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: int
    parameters: dict[str, float | int]
    run_id: str
    snapshot_count: int
    proposal_count: int
    trade_count: int
    winning_trades: int
    losing_trades: int
    win_rate: float | None
    profit_factor: float | None
    total_realized_pnl: float
    final_equity: float
    total_return: float
    max_drawdown: float
    output_dir: str


EngineFactory = Callable[[BacktestConfig], BacktestEngine]
SnapshotLoader = Callable[[], list]


def calculate_max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0

    running_peak = equity.cummax()
    drawdown = equity / running_peak - 1.0
    return float(drawdown.min())


def summarize_engine_run(
    *,
    experiment_id: int,
    parameters: dict[str, float | int],
    engine: BacktestEngine,
    result,
) -> ExperimentResult:
    equity = pd.Series(
        [point["equity"] for point in result.equity_curve],
        index=pd.DatetimeIndex(
            [point["ts"] for point in result.equity_curve],
        ),
        dtype=float,
    )

    trades = engine.portfolio.closed_trades
    pnl = [trade.realized_pnl for trade in trades]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    initial_equity = engine.config.initial_capital
    final_equity = float(equity.iloc[-1]) if not equity.empty else initial_equity

    return ExperimentResult(
        experiment_id=experiment_id,
        parameters=parameters,
        run_id=engine.config.run_id,
        snapshot_count=len(result.decisions),
        proposal_count=result.proposal_count,
        trade_count=len(trades),
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=len(wins) / len(pnl) if pnl else None,
        profit_factor=(
            gross_profit / gross_loss
            if gross_loss > 0
            else (None if gross_profit == 0 else float("inf"))
        ),
        total_realized_pnl=float(sum(pnl)),
        final_equity=final_equity,
        total_return=final_equity / initial_equity - 1.0,
        max_drawdown=calculate_max_drawdown(equity),
        output_dir=str(engine.config.output_dir / engine.config.run_id),
    )


def run_parameter_experiments(
    *,
    base_config: BacktestConfig,
    grid: ParameterGrid,
    engine_factory: EngineFactory,
    snapshot_loader: SnapshotLoader | None = None,
) -> list[ExperimentResult]:
    results: list[ExperimentResult] = []

    # Load and validate the warehouse once, then reuse the same
    # research-grade snapshot stream for every parameter combination.
    warmup_engine = engine_factory(base_config)

    if snapshot_loader is None:
        snapshot_loader = warmup_engine.loader.load_market_hour_snapshots

    snapshots = snapshot_loader()

    print(
        f"Loaded {len(snapshots)} research-grade snapshots; "
        f"running {len(grid.combinations())} experiments",
    )

    for experiment_id, parameters in enumerate(grid.combinations()):
        config = base_config.model_copy(
            update={
                **parameters,
                "run_id": f"{base_config.run_id}_exp{experiment_id:03d}",
            },
        )

        engine = engine_factory(config)
        result = engine.run(snapshots=snapshots)
        engine.save(result)

        experiment_result = summarize_engine_run(
            experiment_id=experiment_id,
            parameters=parameters,
            engine=engine,
            result=result,
        )

        results.append(experiment_result)

        print(
            f"Completed experiment {experiment_id}: "
            f"iv_collapse_pct={parameters['iv_collapse_pct']} "
            f"expected_move_buffer={parameters['expected_move_buffer']} "
            f"entry_cooldown_minutes={parameters['entry_cooldown_minutes']} "
            f"snapshots={experiment_result.snapshot_count} "
            f"trades={experiment_result.trade_count}",
        )

    return results


def save_experiment_results(
    results: list[ExperimentResult],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = [asdict(result) for result in results]
    results_path = output_dir / "parameter_experiments.csv"
    pd.DataFrame(rows).to_csv(results_path, index=False)

    summary = {
        "experiment_count": len(results),
        "research_grade_status": (
            "INSUFFICIENT_DATA_FOR_OPTIMIZATION"
            if results and all(result.snapshot_count < 500 for result in results)
            else "REVIEW_MANUALLY"
        ),
        "results_file": str(results_path),
    }

    summary_path = output_dir / "parameter_experiments_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )

    return results_path, summary_path
