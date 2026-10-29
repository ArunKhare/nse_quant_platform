import pandas as pd

from nse_quant.research.backtest_reporting import compare_experiments
from nse_quant.research.experiment_registry import register_walk_forward_run


def test_register_walk_forward_run(tmp_path):
    results_dir = tmp_path / "run"
    results_dir.mkdir()

    pd.DataFrame(
        [
            {
                "train_dates": "2026-10-20,2026-10-21",
                "test_dates": "2026-10-27",
                "selection_status": "SELECTED",
                "test_trade_count": 2,
                "test_total_realized_pnl": 100.0,
                "selected_iv_collapse_pct": 10.0,
                "selected_expected_move_buffer": 0.75,
                "selected_entry_cooldown_minutes": 30,
            }
        ]
    ).to_csv(results_dir / "walk_forward_results.csv", index=False)

    registry_path = tmp_path / "experiment_index.csv"

    row = register_walk_forward_run(
        results_csv=results_dir / "walk_forward_results.csv",
        registry_path=registry_path,
    )

    saved = pd.read_csv(registry_path)

    assert len(saved) == 1
    assert saved.iloc[0]["run_id"] == "run"
    assert saved.iloc[0]["out_of_sample_trades"] == 2
    assert saved.iloc[0]["out_of_sample_pnl"] == 100.0
    assert row["run_id"] == "run"


def test_compare_experiments_filters_and_ranks(tmp_path):
    registry_path = tmp_path / "experiment_index.csv"
    output_path = tmp_path / "comparison.csv"

    pd.DataFrame(
        [
            {
                "run_id": "small",
                "start_date": "2026-10-18",
                "end_date": "2026-10-29",
                "out_of_sample_trades": 3,
                "out_of_sample_pnl": 700.0,
                "research_grade_status": "INSUFFICIENT_DATA_FOR_OPTIMIZATION",
                "min_iv_rank": 0.0,
                "max_spread_pct": 0.06,
            },
            {
                "run_id": "large_better",
                "start_date": "2026-10-18",
                "end_date": "2026-10-29",
                "out_of_sample_trades": 25,
                "out_of_sample_pnl": 1500.0,
                "research_grade_status": "READY",
                "min_iv_rank": 30.0,
                "max_spread_pct": 0.05,
            },
            {
                "run_id": "large_worse",
                "start_date": "2026-10-18",
                "end_date": "2026-10-29",
                "out_of_sample_trades": 30,
                "out_of_sample_pnl": 500.0,
                "research_grade_status": "READY",
                "min_iv_rank": 30.0,
                "max_spread_pct": 0.05,
            },
        ]
    ).to_csv(registry_path, index=False)

    result = compare_experiments(
        registry_path=registry_path,
        min_trades=20,
        output_path=output_path,
    )

    saved = pd.read_csv(output_path)

    assert list(result["run_id"]) == ["large_better", "large_worse"]
    assert len(saved) == 2
    assert "small" not in set(saved["run_id"])
