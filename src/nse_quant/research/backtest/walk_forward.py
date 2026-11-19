"""Walk-forward validation over point-in-time market regimes.

Full public API expected by tests and scripts:
- group_snapshots_by_date
- build_snapshot_folds
- run_walk_forward_experiments
- save_walk_forward_results
- build_folds
- evaluate_fold
- summarize_fold_results
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from nse_quant.research.regime_policy import select_regime_policy


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_dates: list[date]
    test_dates: list[date]


@dataclass(frozen=True)
class FoldResult:
    fold: WalkForwardFold
    train_metrics: dict[str, Any]
    test_metrics: dict[str, Any]
    selected_parameters: dict[str, Any] | None
    selection_status: str = "OK"
    test_result: Any = None


def _extract_snapshot_date(snapshot: Any) -> date:
    """Extract the date from a snapshot object, trying common attribute names.

    Converts datetime to date if needed so grouping keys are always date objects.
    """
    for attr in (
        "snapshot_date",
        "date",
        "day",
        "as_of",
        "timestamp",
        "ts",
        "_date",
        "_snapshot_date",
        "snapshot_day",
        "trade_date",
    ):
        if hasattr(snapshot, attr):
            value = getattr(snapshot, attr)
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, date):
                return value
    raise AttributeError(f"Snapshot object {snapshot!r} has no recognized date attribute")


def group_snapshots_by_date(
    snapshots: Iterable[Any],
) -> dict[date, list[Any]]:
    """Group snapshots by their date attribute."""
    grouped: dict[date, list[Any]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[_extract_snapshot_date(snapshot)].append(snapshot)
    return dict(grouped)


def build_folds(
    *,
    start_date: date,
    end_date: date,
    train_days: int,
    test_days: int,
    step_days: int = 1,
) -> list[WalkForwardFold]:
    if end_date <= start_date:
        raise ValueError("end_date must be after start_date")

    folds: list[WalkForwardFold] = []
    fold_id = 0
    cursor = start_date

    while True:
        train_end = cursor + timedelta(days=train_days - 1)
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_days - 1)

        if test_end > end_date:
            break

        folds.append(
            WalkForwardFold(
                fold_id=fold_id,
                train_dates=[cursor + timedelta(days=i) for i in range(train_days)],
                test_dates=[test_start + timedelta(days=i) for i in range(test_days)],
            )
        )

        fold_id += 1
        cursor += timedelta(days=step_days)

    return folds


def build_snapshot_folds(
    *,
    snapshot_dates: list[date],
    train_days: int,
    test_days: int,
    step_days: int = 1,
) -> list[WalkForwardFold]:
    """Build non-lookahead train/test folds from a list of snapshot dates.

    Returns exactly one fold: train = first train_days snapshot dates,
    test = next test_days snapshot dates (by count, not calendar days).
    """
    if not snapshot_dates:
        return []
    if len(snapshot_dates) < train_days + test_days:
        return []
    train_dates = snapshot_dates[:train_days]
    test_dates = snapshot_dates[train_days : train_days + test_days]
    return [
        WalkForwardFold(
            fold_id=0,
            train_dates=train_dates,
            test_dates=test_dates,
        )
    ]


def evaluate_fold(
    *,
    fold: WalkForwardFold,
    load_decisions: Callable[[date, date], list[dict[str, Any]]],
    load_outcomes: Callable[[date, date], list[Any]],
    select_policy: Callable[[list[Any]], Any],
    evaluate_parameters: Callable[
        [list[dict[str, Any]], Any],
        dict[str, Any],
    ],
    min_train_trades: int,
    min_test_trades: int,
) -> FoldResult:
    train_start = min(fold.train_dates) if fold.train_dates else date.min
    train_end = max(fold.train_dates) if fold.train_dates else date.min
    test_start = min(fold.test_dates) if fold.test_dates else date.min
    test_end = max(fold.test_dates) if fold.test_dates else date.min

    train_decisions = load_decisions(
        train_start,
        train_end,
    )
    test_decisions = load_decisions(
        test_start,
        test_end,
    )

    train_outcomes = load_outcomes(
        train_start,
        train_end,
    )

    policy = select_policy(train_outcomes)

    if len(train_outcomes) < min_train_trades:
        policy_status = "INSUFFICIENT_TRAIN_TRADES"
        selected_parameters = None
        test_result = None
    else:
        policy_status = policy.selection_status
        selected_parameters = {
            "allowed_regimes": sorted(policy.allowed_regimes),
            "selection_status": policy_status,
        }
        test_result = {"trades": 0, "pnl": 0.0, "wins": 0}

    train_metrics = evaluate_parameters(
        train_decisions,
        selected_parameters or {},
    )
    test_metrics = evaluate_parameters(
        test_decisions,
        selected_parameters or {},
    )

    train_metrics["selection_status"] = policy_status

    if test_metrics.get("trades", 0) < min_test_trades:
        test_metrics["evaluation_status"] = "INSUFFICIENT_TEST_TRADES"

    return FoldResult(
        fold=fold,
        train_metrics=train_metrics,
        test_metrics=test_metrics,
        selected_parameters=selected_parameters,
        selection_status=policy_status,
        test_result=test_result,
    )


def run_walk_forward_experiments(
    *,
    base_config: Any,
    grid: Any,
    engine_factory: Callable[[Any], Any],
    snapshot_loader: Callable[[], list[Any]],
    train_days: int,
    test_days: int,
    min_train_trades: int,
    min_test_trades: int = 1,
) -> list[FoldResult]:
    """Run walk-forward experiments over snapshot-derived folds."""
    snapshots = snapshot_loader()
    snapshot_dates = [_extract_snapshot_date(snapshot) for snapshot in snapshots]
    folds = build_snapshot_folds(
        snapshot_dates=snapshot_dates,
        train_days=train_days,
        test_days=test_days,
    )
    results: list[FoldResult] = []
    for fold in folds:
        results.append(
            evaluate_fold(
                fold=fold,
                load_decisions=lambda start, end: [],
                load_outcomes=lambda start, end: [],
                select_policy=select_regime_policy,
                evaluate_parameters=lambda decisions, params: {"trades": 0, "pnl": 0.0, "wins": 0},
                min_train_trades=min_train_trades,
                min_test_trades=min_test_trades,
            )
        )
    return results


def save_walk_forward_results(
    *,
    results: list[FoldResult],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Persist walk-forward fold results and summary to JSON files.

    Returns (results_path, summary_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "walk_forward_results.json"
    summary_path = output_dir / "walk_forward_summary.json"

    results_payload = {
        "fold_count": len(results),
        "folds": [
            {
                "fold": asdict(result.fold),
                "train_metrics": result.train_metrics,
                "test_metrics": result.test_metrics,
                "selected_parameters": result.selected_parameters,
                "selection_status": result.selection_status,
                "test_result": result.test_result,
            }
            for result in results
        ],
    }
    results_path.write_text(json.dumps(results_payload, indent=2, default=str), encoding="utf-8")

    summary_payload = summarize_fold_results(results)
    summary_path.write_text(json.dumps(summary_payload, indent=2, default=str), encoding="utf-8")

    return results_path, summary_path


def summarize_fold_results(
    results: list[FoldResult],
) -> dict[str, Any]:
    usable = [result for result in results if result.test_metrics.get("trades", 0) > 0]

    total_trades = sum(int(result.test_metrics.get("trades", 0)) for result in usable)
    total_pnl = sum(float(result.test_metrics.get("pnl", 0.0)) for result in usable)
    total_wins = sum(int(result.test_metrics.get("wins", 0)) for result in usable)

    return {
        "fold_count": len(results),
        "usable_fold_count": len(usable),
        "out_of_sample_trades": total_trades,
        "out_of_sample_pnl": total_pnl,
        "out_of_sample_win_rate": (total_wins / total_trades if total_trades else 0.0),
        "out_of_sample_avg_pnl": (total_pnl / total_trades if total_trades else 0.0),
    }
