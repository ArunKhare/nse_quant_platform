"""Walk-forward validation over point-in-time market regimes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from nse_quant.research.regime_policy import select_regime_policy


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date


@dataclass(frozen=True)
class FoldResult:
    fold: WalkForwardFold
    train_metrics: dict[str, Any]
    test_metrics: dict[str, Any]
    selected_parameters: dict[str, Any]


def build_folds(
    *,
    start_date: date,
    end_date: date,
    train_days: int,
    test_days: int,
    step_days: int,
) -> list[WalkForwardFold]:
    """Build non-lookahead train/test folds.

    Each test window begins immediately after its training window. The next
    fold advances by step_days, producing overlapping test windows only when
    step_days is smaller than test_days.
    """
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
                train_start=cursor,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
        )

        fold_id += 1
        cursor += timedelta(days=step_days)

    return folds


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
    train_decisions = load_decisions(
        fold.train_start,
        fold.train_end,
    )
    test_decisions = load_decisions(
        fold.test_start,
        fold.test_end,
    )

    train_outcomes = load_outcomes(
        fold.train_start,
        fold.train_end,
    )

    policy = select_policy(train_outcomes)

    if len(train_outcomes) < min_train_trades:
        policy = select_regime_policy([])
        policy_status = "INSUFFICIENT_TRAIN_TRADES"
    else:
        policy_status = policy.selection_status

    selected_parameters = {
        "allowed_regimes": sorted(policy.allowed_regimes),
        "selection_status": policy_status,
    }

    train_metrics = evaluate_parameters(
        train_decisions,
        selected_parameters,
    )
    test_metrics = evaluate_parameters(
        test_decisions,
        selected_parameters,
    )

    train_metrics["selection_status"] = policy_status

    if test_metrics.get("trades", 0) < min_test_trades:
        test_metrics["evaluation_status"] = "INSUFFICIENT_TEST_TRADES"

    return FoldResult(
        fold=fold,
        train_metrics=train_metrics,
        test_metrics=test_metrics,
        selected_parameters=selected_parameters,
    )


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
