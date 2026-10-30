from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from nse_quant.research.backtest.config import BacktestConfig
from nse_quant.research.backtest.engine import (
    BacktestEngine,
    BacktestResult,
    PreparedFeatureStep,
    PreparedReplayStep,
)
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


def build_snapshot_folds(
    snapshot_dates: list[date],
    *,
    train_days: int,
    test_days: int,
) -> list[WalkForwardFold]:
    unique_dates = sorted(set(snapshot_dates))
    folds: list[WalkForwardFold] = []
    cursor = 0
    fold_id = 0

    while True:
        train_dates = unique_dates[cursor : cursor + train_days]
        test_dates = unique_dates[cursor + train_days : cursor + train_days + test_days]

        if len(train_dates) < train_days or len(test_dates) < test_days:
            break

        folds.append(
            WalkForwardFold(
                fold_id=fold_id,
                train_dates=train_dates,
                test_dates=test_dates,
            )
        )

        fold_id += 1
        cursor += test_days

    return folds


def group_snapshots_by_date(snapshots: list) -> dict[date, list]:
    grouped: dict[date, list] = {}

    for snapshot in snapshots:
        snapshot_date = pd.Timestamp(snapshot.ts).tz_convert("UTC").date()
        grouped.setdefault(snapshot_date, []).append(snapshot)

    return grouped


def _run_train_experiment(
    config: BacktestConfig,
    prepared_features: list[PreparedFeatureStep],
    engine_factory: EngineFactory | None = None,
) -> tuple[BacktestEngine, BacktestResult]:
    engine = engine_factory(config) if engine_factory is not None else BacktestEngine(config)
    result = engine.run_prepared_features(prepared_features)
    engine.save(result)
    return engine, result


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
    workers: int = 1,
) -> list[WalkForwardFoldResult]:
    snapshots = snapshot_loader()
    grouped = group_snapshots_by_date(snapshots)
    available_dates = sorted(grouped)

    folds = build_snapshot_folds(
        available_dates,
        train_days=train_days,
        test_days=test_days,
    )
    print(
        "DEBUG fold construction:",
        f"available_dates={available_dates}",
        f"fold_count={len(folds)}",
        f"train_days={train_days}",
        f"test_days={test_days}",
    )

    results: list[WalkForwardFoldResult] = []

    for fold in folds:
        if snapshots:
            print(
                "DEBUG filter:",
                f"first_snapshot_date= {snapshots[0].ts.date()}",
                f"train_dates = {fold.train_dates}",
                f"match = {snapshots[0].ts.date() in fold.train_dates}",
            )

        train_snapshots = [
            snapshot for snapshot in snapshots if snapshot.ts.date() in fold.train_dates
        ]
        test_snapshots = [
            snapshot for snapshot in snapshots if snapshot.ts.date() in fold.test_dates
        ]

        train_results: list[ExperimentResult] = []

        warmup_engine = engine_factory(base_config)
        ordered_fold_snapshots = [
            *train_snapshots,
            *test_snapshots,
        ]

        prepared_fold_replay, uses_feature_path = _prepare_engine_replay(
            warmup_engine,
            ordered_fold_snapshots,
        )

        prepared_train_replay: list[object] = []
        prepared_test_replay: list[object] = []

        for snapshot, step in zip(
            ordered_fold_snapshots,
            prepared_fold_replay,
            strict=True,
        ):
            if snapshot.ts.date() in fold.train_dates:
                prepared_train_replay.append(step)
            else:
                prepared_test_replay.append(step)

        experiment_configs: list[BacktestConfig] = []
        experiment_parameters: list[dict[str, float | int]] = []

        for experiment_id, parameters in enumerate(grid.combinations()):
            config = base_config.model_copy(
                update={
                    **parameters,
                    "run_id": (
                        f"{base_config.run_id}_fold{fold.fold_id:03d}_train{experiment_id:03d}"
                    ),
                },
            )

            experiment_configs.append(config)
            experiment_parameters.append(parameters)

        max_workers = min(len(experiment_configs), max(1, workers))

        if uses_feature_path:
            if max_workers > 1:
                with ProcessPoolExecutor(max_workers=max_workers) as pool:
                    futures = [
                        pool.submit(
                            _run_train_experiment,
                            config=config,
                            prepared_features=prepared_train_replay,
                        )
                        for config in experiment_configs
                    ]
                    engine_results = [future.result() for future in futures]
            else:
                engine_results = [
                    _run_train_experiment(
                        config=config,
                        prepared_features=prepared_train_replay,
                        engine_factory=engine_factory,
                    )
                    for config in experiment_configs
                ]
        else:
            engine_results = []

            for config in experiment_configs:
                engine = engine_factory(config)
                result = engine.run(prepared_steps=prepared_train_replay)
                engine_results.append((engine, result))

        for experiment_id, (parameters, (engine, result)) in enumerate(
            zip(experiment_parameters, engine_results, strict=True)
        ):
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

            if uses_feature_path:
                test_engine_result = test_engine.run_prepared_features(
                    prepared_test_replay,
                )
            else:
                test_engine_result = test_engine.run(
                    prepared_steps=prepared_test_replay,
                )

            test_engine.save(test_engine_result)
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

    results_columns = [
        "fold_id",
        "train_dates",
        "test_dates",
        "selection_status",
        "train_experiment_count",
        "selected_iv_collapse_pct",
        "selected_expected_move_buffer",
        "selected_entry_cooldown_minutes",
        "test_trade_count",
        "test_total_realized_pnl",
        "test_total_return",
        "test_max_drawdown",
        "test_exit_reason_counts",
    ]

    results_path = output_dir / "walk_forward_results.csv"
    pd.DataFrame(rows, columns=results_columns).to_csv(results_path, index=False)

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


def _prepare_engine_replay(
    engine: BacktestEngine,
    snapshots: list,
) -> tuple[
    list[PreparedFeatureStep] | list[PreparedReplayStep],
    bool,
]:
    """Return prepared replay data and whether it uses the feature path."""
    if hasattr(engine, "prepare_features"):
        return engine.prepare_features(snapshots), True

    return engine.prepare_replay(snapshots), False
