from datetime import date, timedelta

from nse_quant.research.regime_policy import select_regime_policy
from nse_quant.research.walk_forward import (
    build_folds,
    evaluate_fold,
    summarize_fold_results,
)


def test_folds_use_future_test_windows() -> None:
    folds = build_folds(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        train_days=30,
        test_days=10,
        step_days=10,
    )

    assert len(folds) >= 2

    first = folds[0]
    second = folds[1]

    assert first.train_start == date(2025, 1, 1)
    assert first.train_end == date(2025, 1, 30)
    assert first.test_start == date(2025, 1, 31)
    assert first.test_end == date(2025, 2, 9)

    assert second.train_start == date(2025, 1, 11)
    assert second.test_start > second.train_end
    assert second.test_start == second.train_end + timedelta(days=1)


def test_insufficient_train_trades_clears_policy() -> None:
    fold = build_folds(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        train_days=252,
        test_days=63,
        step_days=63,
    )[0]

    result = evaluate_fold(
        fold=fold,
        load_decisions=lambda *_: [],
        load_outcomes=lambda *_: [],
        select_policy=select_regime_policy,
        evaluate_parameters=lambda decisions, parameters: {
            "trades": 0,
            "wins": 0,
            "pnl": 0.0,
        },
        min_train_trades=10,
        min_test_trades=5,
    )

    assert result.selected_parameters["allowed_regimes"] == []
    assert result.selected_parameters["selection_status"] == "INSUFFICIENT_TRAIN_TRADES"
    assert result.train_metrics["selection_status"] == "INSUFFICIENT_TRAIN_TRADES"


def test_summary_handles_no_usable_folds() -> None:
    summary = summarize_fold_results([])

    assert summary["fold_count"] == 0
    assert summary["usable_fold_count"] == 0
    assert summary["out_of_sample_trades"] == 0
