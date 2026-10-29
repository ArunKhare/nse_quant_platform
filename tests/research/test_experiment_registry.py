import pandas as pd

from nse_quant.research.experiment_registry import (
    register_walk_forward_run,
)


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
