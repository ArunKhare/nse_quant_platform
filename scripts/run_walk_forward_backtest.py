from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from datetime import date
from functools import partial
from pathlib import Path
from typing import Protocol

from nse_quant.core.settings import (
    ResearchSettings,
    Settings,
    get_settings,
)
from nse_quant.research.backtest.config import BacktestConfig
from nse_quant.research.backtest.engine import BacktestEngine
from nse_quant.research.backtest.experiments import ParameterGrid
from nse_quant.research.backtest.walk_forward import (
    run_walk_forward_experiments,
    save_walk_forward_results,
)
from nse_quant.research.experiment_registry import register_walk_forward_run
from nse_quant.strategy.iron_condor import IronCondorMonitor


class ExperimentSettings(Protocol):
    @property
    def research(self) -> ResearchSettings: ...


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
    parser.add_argument(
        "--allow-unready-diagnostic",
        action="store_true",
        help="Allow a diagnostic walk-forward run despite incomplete readiness",
    )
    return parser.parse_args()


def make_engine(
    config: BacktestConfig,
    settings: Settings | None = None,
) -> BacktestEngine:
    if settings is None:
        settings = get_settings("config/settings.test.yaml")

    return BacktestEngine(
        config,
        strategy=IronCondorMonitor(settings),
    )


def resolve_experiment_permission(
    *,
    settings: ExperimentSettings,
    readiness: Mapping[str, object],
    allow_unready_diagnostic: bool,
) -> tuple[bool, str]:
    flag_enabled = settings.research.enable_parameter_experiments
    readiness_ready = bool(readiness.get("ready", False))

    if flag_enabled and readiness_ready:
        return True, "research_ready"

    if allow_unready_diagnostic:
        return True, "diagnostic_override"

    return False, "blocked"


def main() -> int:
    args = parse_args()

    settings = get_settings("config/settings.test.yaml")
    readiness_path = Path("data/research/backtest_readiness.json")
    readiness = (
        json.loads(readiness_path.read_text(encoding="utf-8")) if readiness_path.exists() else {}
    )

    experiments_allowed, permission_reason = resolve_experiment_permission(
        settings=settings,
        readiness=readiness,
        allow_unready_diagnostic=args.allow_unready_diagnostic,
    )

    permission_audit = {
        "permission_reason": permission_reason,
        "experiments_allowed": experiments_allowed,
        "allow_unready_diagnostic": args.allow_unready_diagnostic,
        "readiness": readiness,
    }

    audit_dir = Path(args.walk_forward_dir) / args.run_id
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / "permission_audit.json"
    audit_path.write_text(
        json.dumps(permission_audit, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"Experiment permission: {permission_reason}")
    print(f"Permission audit: {audit_path}")
    if not experiments_allowed:
        raise SystemExit(
            "Parameter experiments are blocked: "
            "research flag is disabled or backtest readiness is not satisfied"
        )

    run_type = (
        "diagnostic"
        if args.allow_unready_diagnostic and not readiness.get("ready", False)
        else "walk_forward"
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

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

    snapshot_loader_engine = BacktestEngine(
        base_config,
        strategy=IronCondorMonitor(settings),
    )

    snapshot_loader_engine.loader.load_market_hour_snapshots()

    engine_factory = partial(make_engine, settings=settings)

    results = run_walk_forward_experiments(
        base_config=base_config,
        grid=grid,
        engine_factory=engine_factory,
        snapshot_loader=snapshot_loader_engine.loader.load_market_hour_snapshots,
        train_days=args.train_days,
        test_days=args.test_days,
        min_train_trades=args.min_train_trades,
        min_test_trades=args.min_test_trades,
        workers=args.workers,
    )
    if not results:
        no_fold_dir = Path(args.walk_forward_dir) / args.run_id
        no_fold_dir.mkdir(parents=True, exist_ok=True)

        summary_path = no_fold_dir / "walk_forward_summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "fold_count": 0,
                    "usable_fold_count": 0,
                    "out_of_sample_trades": 0,
                    "out_of_sample_pnl": 0.0,
                    "research_grade_status": "INSUFFICIENT_DATA_FOR_OPTIMIZATION",
                    "reason": (
                        "Insufficient distinct trading dates for walk-forward folds; "
                        f"requires train_days={args.train_days} plus "
                        f"test_days={args.test_days}"
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        print(
            "Walk-forward run skipped: insufficient distinct trading dates "
            f"for {args.train_days} train day(s) and {args.test_days} test day(s)."
        )
        print(f"Summary: {summary_path}")
        return 2
    results_path, summary_path = save_walk_forward_results(
        results=results,
        output_dir=Path(args.walk_forward_dir) / args.run_id,
    )

    register_walk_forward_run(
        results_csv=results_path,
        report_dir=Path("data/research/reports"),
        registry_path=Path("data/research/experiments/experiment_index.csv"),
        underlying=args.symbol,
        min_iv_rank=settings.get_effective_min_iv_rank("iron_condor_monitor"),
        max_spread_pct=settings.get_effective_risk_settings("iron_condor_monitor").max_spread_pct,
        run_type=run_type,
    )
    print("Walk-forward backtest complete")
    print(f"Results: {results_path}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
