from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from nse_quant.research.backtest.experiment_analysis import (
    build_analysis_report,
    load_experiment_results,
    rank_experiments,
    save_analysis_report,
)

EXIT_REASON_COLUMNS = {
    "exit_reason_target_profit": 1,
    "exit_reason_stop_loss": 1,
    "exit_reason_iv_collapse": 0,
    "exit_reason_expected_move_violation": 0,
    "exit_reason_expiry_force_close": 0,
}


def make_results() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "experiment_id": 0,
                "run_id": "run_000",
                "snapshot_count": 674,
                "proposal_count": 3,
                "trade_count": 2,
                "win_rate": 0.5,
                "profit_factor": 2.0,
                "total_realized_pnl": 100.0,
                "final_equity": 1_000_100.0,
                "total_return": 0.0001,
                "max_drawdown": -0.01,
                "iv_collapse_pct": 20.0,
                "expected_move_buffer": 1.25,
                "entry_cooldown_minutes": 15,
                **EXIT_REASON_COLUMNS,
            },
            {
                "experiment_id": 1,
                "run_id": "run_001",
                "snapshot_count": 674,
                "proposal_count": 4,
                "trade_count": 3,
                "win_rate": 0.67,
                "profit_factor": 3.0,
                "total_realized_pnl": 200.0,
                "final_equity": 1_000_200.0,
                "total_return": 0.0002,
                "max_drawdown": -0.02,
                "iv_collapse_pct": 15.0,
                "expected_move_buffer": 1.25,
                "entry_cooldown_minutes": 15,
                **EXIT_REASON_COLUMNS,
            },
        ],
    )


def write_results(tmp_path: Path) -> Path:
    path = tmp_path / "parameter_experiments.csv"
    make_results().to_csv(path, index=False)
    return path


def test_load_experiment_results_requires_required_columns(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"experiment_id": [0]}).to_csv(path, index=False)

    with pytest.raises(ValueError, match="missing required columns"):
        load_experiment_results(path)


def test_rank_experiments_marks_short_runs_ineligible():
    ranked, status = rank_experiments(make_results())

    assert status == "INSUFFICIENT_DATA_FOR_OPTIMIZATION"
    assert not ranked["promotion_eligible"].any()
    assert ranked.iloc[0]["experiment_id"] == 1


def test_rank_experiments_promotes_sufficient_run():
    results = make_results()
    results.loc[0, "trade_count"] = 12

    ranked, status = rank_experiments(results)

    assert status == "SINGLE_CANDIDATE_REVIEW_REQUIRED"
    assert ranked.iloc[0]["experiment_id"] == 0
    assert bool(ranked.iloc[0]["promotion_eligible"]) is True


def test_analysis_report_is_research_only_for_insufficient_data():
    report = build_analysis_report(make_results())

    assert report["analysis_status"] == "INSUFFICIENT_DATA_FOR_OPTIMIZATION"
    assert report["recommendation"] == "RESEARCH_ONLY_DO_NOT_PROMOTE"
    assert report["recommended_experiment_id"] == 1
    assert report["exit_reason_totals"] == {
        "TARGET_PROFIT": 2,
        "STOP_LOSS": 2,
        "IV_COLLAPSE": 0,
        "EXPECTED_MOVE_VIOLATION": 0,
        "EXPIRY_FORCE_CLOSE": 0,
    }


def test_save_analysis_report_writes_outputs(tmp_path):
    results_path = write_results(tmp_path)
    output_dir = tmp_path / "analysis"

    ranked_path, report_path = save_analysis_report(
        results_path=results_path,
        output_dir=output_dir,
    )

    assert ranked_path.exists()
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["experiment_count"] == 2
    assert report["promotion_eligible_count"] == 0
    assert report["recommendation"] == "RESEARCH_ONLY_DO_NOT_PROMOTE"
    assert report["exit_reason_totals"]["TARGET_PROFIT"] == 2


def test_load_experiment_results_flattens_legacy_parameters(tmp_path):
    path = tmp_path / "legacy.csv"

    pd.DataFrame(
        [
            {
                "experiment_id": 0,
                "run_id": "legacy_run",
                "snapshot_count": 614,
                "proposal_count": 1,
                "trade_count": 1,
                "win_rate": 1.0,
                "profit_factor": 2.0,
                "total_realized_pnl": 100.0,
                "final_equity": 1_000_100.0,
                "total_return": 0.0001,
                "max_drawdown": -0.01,
                "parameters": (
                    "{'iv_collapse_pct': 20.0, 'expected_move_buffer': 1.25, "
                    "'entry_cooldown_minutes': 15}"
                ),
            }
        ],
    ).to_csv(path, index=False)

    frame = load_experiment_results(path)

    assert frame.iloc[0]["iv_collapse_pct"] == pytest.approx(20.0)
    assert frame.iloc[0]["expected_move_buffer"] == pytest.approx(1.25)
    assert frame.iloc[0]["entry_cooldown_minutes"] == 15
