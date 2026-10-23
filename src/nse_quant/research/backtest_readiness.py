from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from glob import glob
from pathlib import Path

import duckdb


@dataclass(frozen=True)
class BacktestReadinessReport:
    underlying: str
    warehouse_glob: str
    complete_option_days: int
    iv_rv_aligned_days: int
    regime_days: int
    min_complete_days: int
    min_iv_rv_aligned_days: int
    min_regime_days: int
    ready: bool
    blockers: list[str]


def evaluate_backtest_readiness(
    *,
    warehouse_glob: str,
    regime_glob: str,
    underlying: str,
    min_complete_days: int,
    min_iv_rv_aligned_days: int,
    min_regime_days: int,
) -> BacktestReadinessReport:
    matching_files = glob(warehouse_glob)

    if not matching_files:
        return BacktestReadinessReport(
            underlying=underlying,
            warehouse_glob=warehouse_glob,
            complete_option_days=0,
            iv_rv_aligned_days=0,
            regime_days=0,
            min_complete_days=min_complete_days,
            min_iv_rv_aligned_days=min_iv_rv_aligned_days,
            min_regime_days=min_regime_days,
            ready=False,
            blockers=[f"warehouse_empty: no Parquet files matched {warehouse_glob}"],
        )
    option_files = glob(warehouse_glob)
    regime_files = glob(regime_glob)

    if not option_files:
        return BacktestReadinessReport(
            underlying=underlying,
            warehouse_glob=warehouse_glob,
            complete_option_days=0,
            iv_rv_aligned_days=0,
            regime_days=0,
            min_complete_days=min_complete_days,
            min_iv_rv_aligned_days=min_iv_rv_aligned_days,
            min_regime_days=min_regime_days,
            ready=False,
            blockers=[
                (f"warehouse_empty: no option-stream Parquet files matched {warehouse_glob}")
            ],
        )

    conn = duckdb.connect()

    try:
        complete_option_days_row = conn.execute(
            """
            SELECT COUNT(DISTINCT CAST(ts AS DATE))
            FROM read_parquet(?)
            WHERE underlying = ?
            """,
            [warehouse_glob, underlying],
        ).fetchone()
        complete_option_days = (
            complete_option_days_row[0] if complete_option_days_row is not None else 0
        )

        iv_rv_aligned_days_row = conn.execute(
            """
            WITH option_days AS (
                SELECT
                    CAST(ts AS DATE) AS trading_date,
                    COUNT(*) AS observation_count
                FROM read_parquet(?)
                WHERE underlying = ?
                  AND iv IS NOT NULL
                GROUP BY CAST(ts AS DATE)
            )
            SELECT COUNT(*)
            FROM option_days
            WHERE observation_count > 0
            """,
            [warehouse_glob, underlying],
        ).fetchone()
        iv_rv_aligned_days = iv_rv_aligned_days_row[0] if iv_rv_aligned_days_row is not None else 0

        regime_days = 0
        if regime_files:
            regime_days_row = conn.execute(
                """
                SELECT COUNT(DISTINCT CAST(ts AS DATE))
                FROM read_parquet(?)
                WHERE symbol = ?
                """,
                [regime_glob, underlying],
            ).fetchone()
            regime_days = regime_days_row[0] if regime_days_row is not None else 0
    finally:
        conn.close()

    blockers: list[str] = []

    if complete_option_days < min_complete_days:
        blockers.append(f"complete_option_days={complete_option_days} < {min_complete_days}")

    if iv_rv_aligned_days < min_iv_rv_aligned_days:
        blockers.append(f"iv_rv_aligned_days={iv_rv_aligned_days} < {min_iv_rv_aligned_days}")

    if regime_days < min_regime_days:
        blockers.append(f"regime_days={regime_days} < {min_regime_days}")

    report = BacktestReadinessReport(
        underlying=underlying,
        warehouse_glob=warehouse_glob,
        complete_option_days=complete_option_days,
        iv_rv_aligned_days=iv_rv_aligned_days,
        regime_days=regime_days,
        min_complete_days=min_complete_days,
        min_iv_rv_aligned_days=min_iv_rv_aligned_days,
        min_regime_days=min_regime_days,
        ready=not blockers,
        blockers=blockers,
    )
    return report


def write_report(
    report: BacktestReadinessReport,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(report), indent=2),
        encoding="utf-8",
    )
