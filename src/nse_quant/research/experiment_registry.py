"""experiment registry and comparison layer. This makes every walk-forward run comparable by
data window, configuration, sample size, and research-grade status—preventing invalid
parameter conclusions as your dataset grows
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

REGISTRY_COLUMNS = [
    "registered_at",
    "run_id",
    "run_type",
    "start_date",
    "end_date",
    "underlying",
    "strategy_version",
    "fold_count",
    "usable_fold_count",
    "out_of_sample_trades",
    "out_of_sample_pnl",
    "research_grade_status",
    "selected_iv_collapse_pct",
    "selected_expected_move_buffer",
    "selected_entry_cooldown_minutes",
    "min_iv_rank",
    "max_spread_pct",
    "results_path",
    "report_path",
]


def register_walk_forward_run(
    *,
    results_csv: Path,
    report_dir: Path | None = None,
    registry_path: Path,
    run_type: str = "walk_forward",
    strategy_version: str = "v12",
    underlying: str = "NIFTY",
    min_iv_rank: float | None = None,
    max_spread_pct: float | None = None,
) -> dict[str, object]:
    results = pd.read_csv(results_csv)

    run_id = results_csv.parent.name
    report_path = report_dir / run_id / "performance_summary.json" if report_dir else None

    selected = results[results["selection_status"] == "SELECTED"]

    row = {
        "registered_at": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "run_type": run_type,
        "start_date": results["train_dates"].iloc[0].split(",")[0],
        "end_date": results["test_dates"].iloc[-1],
        "underlying": underlying,
        "strategy_version": strategy_version,
        "fold_count": int(len(results)),
        "usable_fold_count": int(len(selected)),
        "out_of_sample_trades": int(results["test_trade_count"].sum()),
        "out_of_sample_pnl": float(results["test_total_realized_pnl"].sum()),
        "research_grade_status": "INSUFFICIENT_DATA_FOR_OPTIMIZATION",
        "selected_iv_collapse_pct": (
            float(selected["selected_iv_collapse_pct"].mode().iloc[0])
            if not selected.empty
            else None
        ),
        "selected_expected_move_buffer": (
            float(selected["selected_expected_move_buffer"].mode().iloc[0])
            if not selected.empty
            else None
        ),
        "selected_entry_cooldown_minutes": (
            float(selected["selected_entry_cooldown_minutes"].mode().iloc[0])
            if not selected.empty
            else None
        ),
        "min_iv_rank": min_iv_rank,
        "max_spread_pct": max_spread_pct,
        "results_path": str(results_csv),
        "report_path": str(report_path) if report_path else None,
    }

    registry_path.parent.mkdir(parents=True, exist_ok=True)

    if registry_path.exists():
        registry = pd.read_csv(registry_path)
        registry = registry[registry["run_id"] != run_id]
        registry = pd.concat([registry, pd.DataFrame([row])], ignore_index=True)
    else:
        registry = pd.DataFrame([row], columns=REGISTRY_COLUMNS)

    registry.to_csv(registry_path, index=False)
    return row
