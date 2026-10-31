"""Run the daily research workflow with explicit research dates.
uv run python scripts\run_daily_research.py --date 2026-10-30 --walk-forward-start 2026-10-30

uv run python scripts/run_daily_research.py `
    --date 2026-10-30 `
    --walk-forward-start 2026-10-20 `
    --workers 5

"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from subprocess import run


def parse_args(
    argv: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the daily research workflow.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--underlying",
        default="NIFTY",
        help="Underlying used for option-stream export.",
    )
    parser.add_argument(
        "--symbol",
        default="NIFTY",
        help="Research symbol; defaults to --underlying.",
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        required=True,
        help="Option export date and walk-forward end date, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--walk-forward-start",
        type=date.fromisoformat,
        required=True,
        help="Inclusive walk-forward start date, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--start-date",
        type=date.fromisoformat,
        default=None,
        help="Regime export start; defaults to --walk-forward-start.",
    )
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=None,
        help="Regime export end; defaults to --date.",
    )
    parser.add_argument(
        "--warehouse-dir",
        default="data/exports",
        help="Export destination and walk-forward warehouse.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Run identifier; generated when omitted.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/research/backtests",
        help="Backtest output directory used by the report loader.",
    )
    parser.add_argument(
        "--report-dir",
        default="data/research/reports",
        help="QuantStats report output directory.",
    )
    parser.add_argument(
        "--train-days",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--test-days",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-train-trades",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--min-test-trades",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--iv-collapse-pct",
        type=float,
        nargs="+",
        default=[20.0],
    )
    parser.add_argument(
        "--expected-move-buffer",
        type=float,
        nargs="+",
        default=[1.25],
    )
    parser.add_argument(
        "--entry-cooldown-minutes",
        type=int,
        nargs="+",
        default=[15],
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel training workers.",
    )

    args = parser.parse_args(argv)

    if args.symbol is None:
        args.symbol = args.underlying

    if args.start_date is None:
        args.start_date = args.walk_forward_start

    if args.end_date is None:
        args.end_date = args.date

    if args.walk_forward_start > args.date:
        parser.error("--walk-forward-start must be <= --date")

    if args.start_date > args.end_date:
        parser.error("--start-date must be <= --end-date")

    for name in (
        "train_days",
        "test_days",
        "min_train_trades",
        "min_test_trades",
        "workers",
    ):
        if getattr(args, name) < 1:
            option = name.replace("_", "-")
            parser.error(f"--{option} must be >= 1")

    if args.run_id is None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        args.run_id = (
            f"{args.symbol}_"
            f"{args.walk_forward_start.isoformat()}_"
            f"{args.date.isoformat()}_"
            f"{timestamp}"
        )

    return args


def run_step(
    label: str,
    script: str,
    arguments: list[str] | None = None,
    *,
    check: bool = True,
) -> None:
    print(f"\n--- {label} ---", flush=True)

    result = run(
        [
            "uv",
            "run",
            "python",
            script,
            *(arguments or []),
        ],
        check=check,
    )

    if not check and result.returncode != 0:
        print(
            f"Warning: {label} exited with code {result.returncode}.",
            flush=True,
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    print(f"Run ID: {args.run_id}", flush=True)
    print(
        "Walk-forward window: "
        f"{args.walk_forward_start.isoformat()} "
        f"through {args.date.isoformat()}",
        flush=True,
    )

    run_step(
        "1. Export option stream",
        "scripts/backfill_option_stream_exports.py",
        [
            "--underlying",
            args.underlying,
            "--date",
            args.date.isoformat(),
            "--export-dir",
            args.warehouse_dir,
        ],
    )

    run_step(
        "2. Export market regimes",
        "scripts/backfill_market_regime_exports.py",
        [
            "--symbol",
            args.symbol,
            "--start-date",
            args.start_date.isoformat(),
            "--end-date",
            args.end_date.isoformat(),
            "--export-dir",
            args.warehouse_dir,
        ],
    )

    run_step(
        "3. Check research readiness",
        "scripts/backtest_readiness.py",
    )

    run_step(
        "4. Run walk-forward experiments",
        "scripts/run_walk_forward_backtest.py",
        [
            "--warehouse-dir",
            args.warehouse_dir,
            "--output-dir",
            args.output_dir,
            "--symbol",
            args.symbol,
            "--start-date",
            args.walk_forward_start.isoformat(),
            "--end-date",
            args.date.isoformat(),
            "--run-id",
            args.run_id,
            "--train-days",
            str(args.train_days),
            "--test-days",
            str(args.test_days),
            "--min-train-trades",
            str(args.min_train_trades),
            "--min-test-trades",
            str(args.min_test_trades),
            "--iv-collapse-pct",
            *map(str, args.iv_collapse_pct),
            "--expected-move-buffer",
            *map(str, args.expected_move_buffer),
            "--entry-cooldown-minutes",
            *map(str, args.entry_cooldown_minutes),
            "--workers",
            str(args.workers),
        ],
    )

    run_step(
        "5. Generate QuantStats report",
        "scripts/generate_backtest_report.py",
        [
            "--run-id",
            args.run_id,
            "--backtest-dir",
            args.output_dir,
            "--output-dir",
            args.report_dir,
        ],
    )

    run_step(
        "6. Generate daily status digest",
        "scripts/research_status_digest.py",
        check=False,
    )

    print("\nDaily research workflow completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
