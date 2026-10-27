from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from nse_quant.research.backtest.config import BacktestConfig
from nse_quant.research.backtest.engine import BacktestEngine
from nse_quant.research.backtest.experiment_analysis import (
    build_analysis_report,
    rank_experiments,
)
from nse_quant.research.backtest.experiments import (
    ExperimentResult,
    ParameterGrid,
    summarize_engine_run,
)

EngineFactory = Callable[[BacktestConfig], BacktestEngine]
SnapshotLoader = Callable[[], list]


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_dates: list[date]
    test_dates: list[date]


@dataclass(frozen=True)
class WalkForwardFoldResult:
    fold_id: int
    train_dates: list[date]
    test_dates: list[date]
    selected_parameters: dict[str, float | int] | None
    selection_status: str
    train_experiment_count: int
    train_metrics: dict[str, object]
    test_result: ExperimentResult | None


def build_date_folds(
    *,
    available_dates: list[date],
    train_days: int,
    test_days: int,
) -> list[WalkForwardFold]:
    if train_days <= 0 or test_days <= 0:
        raise ValueError("train_days and test_days must be positive")

    dates = sorted(set(available_dates))
    folds: list[WalkForwardFold] = []

    for start in range(len(dates) - train_days - test_days + 1):
        train_dates = dates[start : start + train_days]
        test_dates = dates[start + train_days : start + train_days + test_days]

        folds.append(
            WalkForwardFold(
                fold_id=start,
                train_dates=train_dates,
                test_dates=test_dates,
            )
        )

    return folds


def group_snapshots_by_date(snapshots: list) -> dict[date, list]:
    grouped: dict[date, list] = {}

    for snapshot in snapshots:
        snapshot_date = pd.Timestamp(snapshot.ts).tz_convert("UTC").date()
        grouped.setdefault(snapshot_date, []).append(snapshot)

    return grouped


def run_walk_forward_experiments(
    *,
    base_config: BacktestConfig,
    grid: ParameterGrid,
    engine_factory: EngineFactory,
    snapshot_loader: SnapshotLoader,
    train_days: int = 2,
    test_days: int = 1,
    min_train_trades: int = 10,
    min_test_trades: int = 1,
) -> list[WalkForwardFoldResult]:
    snapshots = snapshot_loader()
    grouped = group_snapshots_by_date(snapshots)
    available_dates = sorted(grouped)

    folds = build_date_folds(
        available_dates=available_dates,
        train_days=train_days,
        test_days=test_days,
    )

    results: list[WalkForwardFoldResult] = []

    for fold in folds:
        train_snapshots = [
            snapshot for train_date in fold.train_dates for snapshot in grouped[train_date]
        ]
        test_snapshots = [
            snapshot for test_date in fold.test_dates for snapshot in grouped[test_date]
        ]

        warmup_engine = engine_factory(base_config)
        prepared_train_steps = warmup_engine.prepare_replay(train_snapshots)

        train_results: list[ExperimentResult] = []

        for experiment_id, parameters in enumerate(grid.combinations()):
            config = base_config.model_copy(
                update={
                    **parameters,
                    "run_id": (
                        f"{base_config.run_id}_fold{fold.fold_id:03d}_train{experiment_id:03d}"
                    ),
                },
            )

            engine = engine_factory(config)
            result = engine.run(prepared_steps=prepared_train_steps)
            engine.save(result)

            train_results.append(
                summarize_engine_run(
                    experiment_id=experiment_id,
                    parameters=parameters,
                    engine=engine,
                    result=result,
                )
            )

        train_frame = results_to_frame(train_results)

        ranked, status = rank_experiments(
            train_frame,
            min_trades=min_train_trades,
            min_snapshots=1,
        )

        eligible = ranked[ranked["promotion_eligible"]]

        if eligible.empty:
            selected_parameters = None
            selection_status = "INSUFFICIENT_TRAIN_TRADES"
            test_result = None
        else:
            selected = eligible.iloc[0]
            selected_parameters = {
                "iv_collapse_pct": float(selected["iv_collapse_pct"]),
                "expected_move_buffer": float(selected["expected_move_buffer"]),
                "entry_cooldown_minutes": int(selected["entry_cooldown_minutes"]),
            }
            selection_status = "SELECTED"

            test_config = base_config.model_copy(
                update={
                    **selected_parameters,
                    "run_id": (f"{base_config.run_id}_fold{fold.fold_id:03d}_test"),
                },
            )

            test_engine = engine_factory(test_config)
            prepared_test_steps = test_engine.prepare_replay(test_snapshots)
            test_engine_result = test_engine.run(
                prepared_steps=prepared_test_steps,
            )
            test_engine.save(test_engine_result)

            test_result = summarize_engine_run(
                experiment_id=0,
                parameters=selected_parameters,
                engine=test_engine,
                result=test_engine_result,
            )

            if test_result.trade_count < min_test_trades:
                selection_status = "SELECTED_INSUFFICIENT_TEST_TRADES"

        analysis = build_analysis_report(
            train_frame,
            min_trades=min_train_trades,
            min_snapshots=1,
        )

        results.append(
            WalkForwardFoldResult(
                fold_id=fold.fold_id,
                train_dates=fold.train_dates,
                test_dates=fold.test_dates,
                selected_parameters=selected_parameters,
                selection_status=selection_status,
                train_experiment_count=len(train_results),
                train_metrics=analysis,
                test_result=test_result,
            )
        )

    return results


def save_walk_forward_results(
    results: list[WalkForwardFoldResult],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []

    for result in results:
        test = result.test_result

        rows.append(
            {
                "fold_id": result.fold_id,
                "train_dates": ",".join(value.isoformat() for value in result.train_dates),
                "test_dates": ",".join(value.isoformat() for value in result.test_dates),
                "selection_status": result.selection_status,
                "train_experiment_count": result.train_experiment_count,
                "selected_iv_collapse_pct": (
                    result.selected_parameters["iv_collapse_pct"]
                    if result.selected_parameters
                    else None
                ),
                "selected_expected_move_buffer": (
                    result.selected_parameters["expected_move_buffer"]
                    if result.selected_parameters
                    else None
                ),
                "selected_entry_cooldown_minutes": (
                    result.selected_parameters["entry_cooldown_minutes"]
                    if result.selected_parameters
                    else None
                ),
                "test_trade_count": test.trade_count if test else 0,
                "test_total_realized_pnl": (test.total_realized_pnl if test else None),
                "test_total_return": test.total_return if test else None,
                "test_max_drawdown": test.max_drawdown if test else None,
                "test_exit_reason_counts": (json.dumps(test.exit_reason_counts) if test else "{}"),
            }
        )

    results_path = output_dir / "walk_forward_results.csv"
    pd.DataFrame(rows).to_csv(results_path, index=False)

    usable_test_results = [
        test_result
        for result in results
        if (test_result := result.test_result) is not None and test_result.trade_count > 0
    ]

    total_test_trades = sum(test_result.trade_count for test_result in usable_test_results)
    total_test_pnl = sum(test_result.total_realized_pnl for test_result in usable_test_results)

    summary = {
        "fold_count": len(results),
        "usable_fold_count": len(usable_test_results),
        "out_of_sample_trades": total_test_trades,
        "out_of_sample_pnl": total_test_pnl,
        "research_grade_status": (
            "INSUFFICIENT_DATA_FOR_OPTIMIZATION"
            if total_test_trades < 10
            else "MANUAL_REVIEW_REQUIRED"
        ),
        "results_file": str(results_path),
    }

    summary_path = output_dir / "walk_forward_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )

    return results_path, summary_path


def results_to_frame(results: list[ExperimentResult]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for result in results:
        row = asdict(result)
        parameters = row.pop("parameters")
        row.pop("exit_reason_totals", None)

        rows.append(
            {
                **row,
                **parameters,
            }
        )

    return pd.DataFrame(rows)
