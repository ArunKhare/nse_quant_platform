import argparse
from subprocess import run

parser = argparse.ArgumentParser(description="Run the daily research workflow.")
parser.add_argument("--underlying", required=True)
parser.add_argument("--date", required=True)
parser.add_argument("--symbol", required=True)
parser.add_argument("--start-date", required=True)
parser.add_argument("--end-date", required=True)
parser.add_argument("--warehouse-dir", required=True)
parser.add_argument("--walk-forward-start", required=True)
parser.add_argument("--run-id", required=True)
parser.add_argument("--output-dir", required=True)
parser.add_argument("--train-days", type=int, required=True)
parser.add_argument("--test-days", type=int, required=True)
parser.add_argument("--min-train-trades", type=int, required=True)
parser.add_argument("--min-test-trades", type=int, required=True)
parser.add_argument("--iv-collapse-pct", type=float, nargs="+", required=True)
parser.add_argument("--expected-move-buffer", type=float, nargs="+", required=True)
parser.add_argument("--entry-cooldown-minutes", type=int, nargs="+", required=True)
parser.add_argument("--workers", type=int, required=True)
args = parser.parse_args()


# 1. Export option stream
run(
    [
        "uv",
        "run",
        "python",
        "scripts/backfill_option_stream_exports.py",
        "--underlying",
        args.underlying,
        "--date",
        args.date,
    ],
    check=True,
)

# 2. Export market regimes
run(
    [
        "uv",
        "run",
        "python",
        "scripts/backfill_market_regime_exports.py",
        "--symbol",
        args.symbol,
        "--start-date",
        args.start_date,
        "--end-date",
        args.end_date,
    ],
    check=True,
)

# 3. Readiness
run(
    [
        "uv",
        "run",
        "python",
        "scripts/backtest_readiness.py",
    ],
    check=True,
)

# 4. Walk-forward
run(
    [
        "uv",
        "run",
        "python",
        "scripts/run_walk_forward_backtest.py",
        "--warehouse-dir",
        args.warehouse_dir,
        "--symbol",
        args.symbol,
        "--start-date",
        args.walk_forward_start,
        "--end-date",
        args.date,
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
    check=True,
)

# 5. QuantStats report
run(
    [
        "uv",
        "run",
        "python",
        "scripts/generate_backtest_report.py",
        "--run-id",
        args.run_id,
        "--backtest-dir",
        args.output_dir,
        "--output-dir",
        "data/research/reports",
    ],
    check=True,
)

# 6. Daily status digest
run(
    [
        "uv",
        "run",
        "python",
        "scripts/research_status_digest.py",
    ],
    check=False,
)
