from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from nse_quant.research.backtest.config import BacktestConfig
from nse_quant.research.backtest.engine import BacktestEngine
from nse_quant.research.backtest.experiments import ParameterGrid
from nse_quant.research.backtest.walk_forward import (
    run_walk_forward_experiments,
    save_walk_forward_results,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run paper-only walk-forward backtest parameter validation.",
    )

    parser.add_argument("--warehouse-dir", default="data/exports")
    parser.add_argument("--output-dir", default="data/research/backtests")
    parser.add_argument("--walk-forward-dir", default="data/research/walk_forward")
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    parser.add_argument("--run-id", required=True)

    parser.add_argument("--train-days", type=int, default=2)
    parser.add_argument("--test-days", type=int, default=1)
    parser.add_argument("--min-train-trades", type=int, default=10)
    parser.add_argument("--min-test-trades", type=int, default=1)

    parser.add_argument("--iv-collapse-pct", nargs="+", type=float, default=[20.0])
    parser.add_argument("--expected-move-buffer", nargs="+", type=float, default=[1.25])
    parser.add_argument("--entry-cooldown-minutes", nargs="+", type=int, default=[15])
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel worker processes for training experiments.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    base_config = BacktestConfig(
        warehouse_dir=Path(args.warehouse_dir),
        output_dir=Path(args.output_dir),
        underlying=args.symbol,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        initial_capital=args.initial_capital,
        run_id=args.run_id,
        min_snapshots=30,
    )

    grid = ParameterGrid(
        iv_collapse_pct=tuple(args.iv_collapse_pct),
        expected_move_buffer=tuple(args.expected_move_buffer),
        entry_cooldown_minutes=tuple(args.entry_cooldown_minutes),
    )

    # DEDUG SCRIPTS
    snapshot_loader = BacktestEngine(base_config)
    snapshots = snapshot_loader.loader.load_market_hour_snapshots()
    print(f"DEBUG snapshot_count={len(snapshots)}")

    if snapshots:
        dates = sorted({pd.Timestamp(s.ts).tz_convert("UTC").date() for s in snapshots})
        print(f"DEBUG snapshot_dates={dates}")
    else:
        print("DEBUG snapshot_loader returned no snapshots")
    print(
        "DEBUG thresholds:",
        base_config.min_snapshots,
        base_config.min_iv_coverage,
    )
    # DEDUG SCRIPTS ENDS

    results = run_walk_forward_experiments(
        base_config=base_config,
        grid=grid,
        engine_factory=BacktestEngine,
        snapshot_loader=BacktestEngine(
            base_config,
        ).loader.load_market_hour_snapshots,
        train_days=args.train_days,
        test_days=args.test_days,
        min_train_trades=args.min_train_trades,
        min_test_trades=args.min_test_trades,
        workers=args.workers,
    )

    results_path, summary_path = save_walk_forward_results(
        results=results,
        output_dir=Path(args.walk_forward_dir) / args.run_id,
    )

    print("Walk-forward backtest complete")
    print(f"Results: {results_path}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
