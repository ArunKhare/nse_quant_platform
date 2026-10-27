from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {
    "experiment_id",
    "run_id",
    "snapshot_count",
    "proposal_count",
    "trade_count",
    "win_rate",
    "profit_factor",
    "total_realized_pnl",
    "final_equity",
    "total_return",
    "max_drawdown",
}

PARAMETER_COLUMNS = {
    "iv_collapse_pct",
    "expected_move_buffer",
    "entry_cooldown_minutes",
}


def flatten_parameters(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()

    if PARAMETER_COLUMNS.issubset(frame.columns):
        return frame

    if "parameters" not in frame.columns:
        raise ValueError(
            "Experiment results must contain either flattened parameter "
            "columns or a 'parameters' column.",
        )

    parsed = frame["parameters"].apply(
        lambda value: ast.literal_eval(value) if isinstance(value, str) else value,
    )

    parameter_frame = pd.json_normalize(parsed)

    return pd.concat(
        [frame.drop(columns=["parameters"]), parameter_frame],
        axis=1,
    )


def load_experiment_results(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)

    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(
            f"Experiment results missing required columns: {sorted(missing)}",
        )

    return flatten_parameters(frame)


def rank_experiments(
    results: pd.DataFrame,
    *,
    min_trades: int = 10,
    min_snapshots: int = 500,
) -> tuple[pd.DataFrame, str]:
    frame = results.copy()

    frame["promotion_eligible"] = (
        (frame["trade_count"] >= min_trades)
        & (frame["snapshot_count"] >= min_snapshots)
        & frame["win_rate"].notna()
        & frame["profit_factor"].notna()
        & (frame["profit_factor"] != float("inf"))
    )

    # Conservative research ordering:
    # 1. Enough observations.
    # 2. Positive realized P&L.
    # 3. Higher profit factor.
    # 4. Smaller drawdown.
    frame = frame.sort_values(
        by=[
            "promotion_eligible",
            "total_realized_pnl",
            "profit_factor",
            "max_drawdown",
        ],
        ascending=[
            False,
            False,
            False,
            True,
        ],
        na_position="last",
    ).reset_index(drop=True)

    eligible_count = int(frame["promotion_eligible"].sum())

    if eligible_count == 0:
        status = "INSUFFICIENT_DATA_FOR_OPTIMIZATION"
    elif eligible_count == 1:
        status = "SINGLE_CANDIDATE_REVIEW_REQUIRED"
    else:
        status = "MULTIPLE_CANDIDATES_REVIEW_REQUIRED"

    return frame, status


def build_analysis_report(
    results: pd.DataFrame,
    *,
    min_trades: int = 10,
    min_snapshots: int = 500,
) -> dict[str, object]:
    ranked, status = rank_experiments(
        results,
        min_trades=min_trades,
        min_snapshots=min_snapshots,
    )

    top = ranked.iloc[0] if not ranked.empty else None

    return {
        "analysis_status": status,
        "experiment_count": int(len(ranked)),
        "promotion_eligible_count": int(ranked["promotion_eligible"].sum()),
        "minimum_trades": min_trades,
        "minimum_snapshots": min_snapshots,
        "recommended_experiment_id": (int(top["experiment_id"]) if top is not None else None),
        "recommended_run_id": (str(top["run_id"]) if top is not None else None),
        "recommended_parameters": (
            {
                "iv_collapse_pct": float(top["iv_collapse_pct"]),
                "expected_move_buffer": float(top["expected_move_buffer"]),
                "entry_cooldown_minutes": int(top["entry_cooldown_minutes"]),
            }
            if top is not None
            else None
        ),
        "recommendation": (
            "RESEARCH_ONLY_DO_NOT_PROMOTE"
            if status == "INSUFFICIENT_DATA_FOR_OPTIMIZATION"
            else "MANUAL_REVIEW_REQUIRED"
        ),
        "exit_reason_totals": summarize_exit_reasons(ranked),
    }


def save_analysis_report(
    results_path: Path,
    output_dir: Path,
    *,
    min_trades: int = 10,
    min_snapshots: int = 500,
) -> tuple[Path, Path]:
    results = load_experiment_results(results_path)
    report = build_analysis_report(
        results,
        min_trades=min_trades,
        min_snapshots=min_snapshots,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    ranked, _ = rank_experiments(
        results,
        min_trades=min_trades,
        min_snapshots=min_snapshots,
    )

    ranked_path = output_dir / "experiment_ranking.csv"
    ranked.to_csv(ranked_path, index=False)

    report_path = output_dir / "experiment_analysis.json"
    report_path.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )

    return ranked_path, report_path


def summarize_exit_reasons(frame: pd.DataFrame) -> dict[str, int]:
    reason_columns = [
        column
        for column in frame.columns
        if column.startswith("exit_reason_") and pd.api.types.is_numeric_dtype(frame[column])
    ]

    return {
        column.removeprefix("exit_reason_").upper(): int(frame[column].sum())
        for column in reason_columns
    }
