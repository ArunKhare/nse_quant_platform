"""Inspect IV/Greeks coverage and orchestrate safe backfills.

This script reports IV, Greeks, raw-input, and multi-expiry IV-surface
coverage for persisted option-stream data. It can optionally invoke the
focused backfill scripts to repair missing values.

Default behavior is report-only. Repair mode fills only missing IV or Greeks;
it never overwrites existing IV or Greeks, downloads market data, creates
missing snapshots, or interpolates absent raw inputs.

Examples
--------

Report coverage for a date range:

.. code-block:: powershell

    uv run python scripts/iv_progress.py `
      --underlying NIFTY `
      --from 2026-10-18 `
      --to 2026-11-19

Report coverage for one trading date:

.. code-block:: powershell

    uv run python scripts/iv_progress.py `
      --underlying NIFTY `
      --trade-date 2026-11-19

Show the repair plan without writing:

.. code-block:: powershell

    uv run python scripts/iv_progress.py `
      --underlying NIFTY `
      --trade-date 2026-11-19 `
      --mode plan

Repair missing IV, Greeks, and underlying ATM IV history:

.. code-block:: powershell

    uv run python scripts/iv_progress.py `
      --underlying NIFTY `
      --trade-date 2026-11-19 `
      --mode repair
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd

from nse_quant.persistence.duckdb_store import DuckDBStore

IST = ZoneInfo("Asia/Kolkata")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect IV/Greeks coverage and orchestrate safe backfills.",
    )
    parser.add_argument(
        "--underlying",
        default="NIFTY",
    )
    parser.add_argument(
        "--trade-date",
        type=date.fromisoformat,
        default=None,
        help=("Optional single trading date in YYYY-MM-DD format. If supplied, it overrides --from and --to."),
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        type=date.fromisoformat,
        default=None,
        help="Start date in YYYY-MM-DD format; required when --trade-date is omitted.",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        type=date.fromisoformat,
        default=None,
        help="End date in YYYY-MM-DD format; required when --trade-date is omitted.",
    )
    parser.add_argument(
        "--mode",
        choices=["report", "plan", "repair"],
        default="report",
        help=("report: coverage only; plan: show repair commands; repair: run safe null-only backfills."),
    )
    parser.add_argument(
        "--risk-free-rate",
        type=float,
        default=0.065,
        help="Risk-free rate passed to the Greeks backfill.",
    )
    return parser.parse_args()


def resolve_date_range(
    args: argparse.Namespace,
) -> tuple[date, date]:
    if args.trade_date is not None:
        return args.trade_date, args.trade_date

    if args.from_date is None or args.to_date is None:
        raise SystemExit("Provide either --trade-date or both --from and --to.")

    if args.to_date < args.from_date:
        raise SystemExit("--to must be on or after --from")

    return args.from_date, args.to_date


def print_section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def coverage(
    store: DuckDBStore,
    underlying: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    return store.conn.execute(
        """
        SELECT
            CAST(ts AS DATE) AS trading_date,
            COUNT(*) AS total_rows,
            COUNT(DISTINCT expiry) AS expiry_count,
            COUNT(iv) AS iv_present,
            COUNT(*) - COUNT(iv) AS iv_missing,
            COUNT(delta) AS delta_present,
            COUNT(*) - COUNT(delta) AS delta_missing,
            COUNT(gamma) AS gamma_present,
            COUNT(*) - COUNT(gamma) AS gamma_missing,
            COUNT(vega) AS vega_present,
            COUNT(*) - COUNT(vega) AS vega_missing,
            COUNT(theta) AS theta_present,
            COUNT(*) - COUNT(theta) AS theta_missing,
            COUNT(*) FILTER (
                WHERE iv IS NULL
                AND ltp IS NOT NULL
                AND ltp > 0
                AND spot IS NOT NULL
            ) AS iv_repairable,
            COUNT(*) FILTER (
                WHERE iv IS NOT NULL
                AND iv > 0
                AND spot IS NOT NULL
                AND (
                    delta IS NULL
                    OR gamma IS NULL
                    OR vega IS NULL
                    OR theta IS NULL
                )
            ) AS greeks_repairable,
            COUNT(*) FILTER (
                WHERE ltp IS NULL
                OR ltp <= 0
                OR spot IS NULL
            ) AS raw_input_missing
        FROM option_stream
        WHERE underlying = ?
          AND CAST(ts AS DATE) BETWEEN ? AND ?
        GROUP BY CAST(ts AS DATE)
        ORDER BY trading_date
        """,
        [underlying, start_date, end_date],
    ).fetchdf()


def surface_readiness(
    store: DuckDBStore,
    underlying: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    return store.conn.execute(
        """
        WITH snapshots AS (
            SELECT
                ts,
                COUNT(DISTINCT expiry) AS expiry_count,
                COUNT(iv) AS iv_count,
                COUNT(delta) AS delta_count,
                COUNT(*) FILTER (WHERE ltp > 0) AS positive_ltp_count
            FROM option_stream
            WHERE underlying = ?
              AND CAST(ts AS DATE) BETWEEN ? AND ?
            GROUP BY ts
        )
        SELECT
            CAST(ts AS DATE) AS trading_date,
            COUNT(*) AS snapshots,
            COUNT(*) FILTER (
                WHERE expiry_count >= 2
                AND iv_count > 0
                AND delta_count > 0
                AND positive_ltp_count > 0
            ) AS surface_ready_snapshots,
            COUNT(*) FILTER (WHERE expiry_count < 2) AS missing_second_expiry,
            COUNT(*) FILTER (WHERE delta_count = 0) AS missing_delta_snapshots
        FROM snapshots
        GROUP BY CAST(ts AS DATE)
        ORDER BY trading_date
        """,
        [underlying, start_date, end_date],
    ).fetchdf()


def run_command(command: list[str]) -> int:
    print("+", " ".join(command))
    return subprocess.run(command, check=False).returncode


def main() -> int:
    args = parse_args()
    start_date, end_date = resolve_date_range(args)

    store = DuckDBStore()

    try:
        daily = coverage(store, args.underlying, start_date, end_date)
        surface = surface_readiness(store, args.underlying, start_date, end_date)
    finally:
        store.close()

    print_section("Daily IV / Greeks coverage")
    print(daily.to_string(index=False))

    print_section("IV-surface readiness")
    print(surface.to_string(index=False))

    iv_gaps = int(daily["iv_repairable"].sum())
    greeks_gaps = int(daily["greeks_repairable"].sum())
    raw_gaps = int(daily["raw_input_missing"].sum())

    print_section("Repair assessment")
    print(f"Repairable IV gaps: {iv_gaps}")
    print(f"Repairable Greeks gaps: {greeks_gaps}")
    print(f"Unrepairable raw-input gaps: {raw_gaps}")

    if args.trade_date is not None:
        greeks_date_args = [
            "--trade-date",
            args.trade_date.isoformat(),
        ]
    else:
        greeks_date_args = [
            "--from",
            f"{start_date}T00:00:00+05:30",
            "--to",
            f"{end_date}T23:59:59+05:30",
        ]

    iv_command = [
        sys.executable,
        "scripts/backfill_option_iv.py",
        "--underlying",
        args.underlying,
        "--from",
        f"{start_date}T00:00:00+05:30",
        "--to",
        f"{end_date}T23:59:59+05:30",
    ]

    greeks_command = [
        sys.executable,
        "scripts/backfill_option_greeks.py",
        "--underlying",
        args.underlying,
        *greeks_date_args,
        "--risk-free-rate",
        str(args.risk_free_rate),
    ]

    atm_command = [
        sys.executable,
        "scripts/backfill_iv.py",
        "--underlying",
        args.underlying,
        "--from",
        f"{start_date}T00:00:00+05:30",
        "--to",
        f"{end_date}T23:59:59+05:30",
    ]

    print_section("Recommended repairs")
    print("+", " ".join(iv_command))
    print("+", " ".join(greeks_command))
    print("+", " ".join(atm_command))

    if args.mode == "repair":
        if iv_gaps:
            run_command(iv_command)

        if greeks_gaps:
            run_command(greeks_command)

        run_command(atm_command)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
