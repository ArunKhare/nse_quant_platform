from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from nse_quant.research.backtest.config import BacktestConfig
from nse_quant.research.backtest.engine import BacktestEngine
from nse_quant.research.backtest.experiments import (
    ParameterGrid,
    run_parameter_experiments,
    save_experiment_results,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run paper-only iron-condor parameter experiments.",
    )

    parser.add_argument("--warehouse-dir", default="data/exports")
    parser.add_argument("--output-dir", default="data/research/backtests")
    parser.add_argument("--experiment-dir", default="data/research/experiments")
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    parser.add_argument("--run-id", default=None)

    parser.add_argument(
        "--iv-collapse-pct",
        nargs="+",
        type=float,
        default=[20.0],
    )
    parser.add_argument(
        "--expected-move-buffer",
        nargs="+",
        type=float,
        default=[1.25],
    )
    parser.add_argument(
        "--entry-cooldown-minutes",
        nargs="+",
        type=int,
        default=[15],
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
        **({"run_id": args.run_id} if args.run_id else {}),
    )

    grid = ParameterGrid(
        iv_collapse_pct=tuple(args.iv_collapse_pct),
        expected_move_buffer=tuple(args.expected_move_buffer),
        entry_cooldown_minutes=tuple(args.entry_cooldown_minutes),
    )

    results = run_parameter_experiments(
        base_config=base_config,
        grid=grid,
        engine_factory=lambda config: BacktestEngine(config),
    )

    results_path, summary_path = save_experiment_results(
        results=results,
        output_dir=Path(args.experiment_dir) / (args.run_id or date.today().isoformat()),
    )

    print("Parameter experiments complete")
    print(f"Experiments: {len(results)}")
    print(f"Results: {results_path}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
