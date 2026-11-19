"""Explicit offline daily/EOD CLI. Planning is the default and does not write files."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from nse_quant.data_platform.workspace_workflows import OfflineWorkflow, WorkflowOptions


def parse_args(kind: str, argv: list[str] | None = None) -> WorkflowOptions:
    parser = argparse.ArgumentParser(description=f"Audited isolated {kind} workflow")
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, default=Path("data/workflow_runs"))
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--source-offline", action="store_true")
    if kind == "daily":
        parser.add_argument("--date", type=date.fromisoformat, required=True)
        parser.add_argument("--walk-forward-start", type=date.fromisoformat, required=True)
        for name, default in (
            ("train-days", 2),
            ("test-days", 1),
            ("min-train-trades", 10),
            ("min-test-trades", 1),
            ("workers", 1),
        ):
            parser.add_argument("--" + name, type=int, default=default)
        parser.add_argument("--iv-collapse-pct", type=float, nargs="+", default=[20.0])
        parser.add_argument("--expected-move-buffer", type=float, nargs="+", default=[1.25])
        parser.add_argument("--entry-cooldown-minutes", type=int, nargs="+", default=[15])
    else:
        parser.add_argument("--trade-date", type=date.fromisoformat, required=True)
        parser.add_argument("--skip-export", action="store_true")
        parser.add_argument("--candle-intervals", default="5m,15m,30m,60m")
    args = parser.parse_args(argv)
    start = args.walk_forward_start if kind == "daily" else args.trade_date
    end = args.date if kind == "daily" else args.trade_date
    base = WorkflowOptions(
        kind=kind,
        source_db=args.source_db.resolve(),
        repository=args.repository.resolve(),
        run_root=args.run_root.resolve(),
        symbol=args.symbol,
        code_revision=args.code_revision,
        actor=args.actor,
        config=args.config.resolve(),
        execute=args.execute,
        source_offline=args.source_offline,
        start_date=start,
        end_date=end,
    )
    if kind == "daily":
        return replace(
            base,
            train_days=args.train_days,
            test_days=args.test_days,
            min_train_trades=args.min_train_trades,
            min_test_trades=args.min_test_trades,
            workers=args.workers,
            iv_collapse_pct=tuple(args.iv_collapse_pct),
            expected_move_buffer=tuple(args.expected_move_buffer),
            entry_cooldown_minutes=tuple(args.entry_cooldown_minutes),
        )
    return replace(base, skip_export=args.skip_export, intervals=args.candle_intervals)


def main(kind: str, argv: list[str] | None = None) -> int:
    options = parse_args(kind, argv)
    report = OfflineWorkflow(options).run()
    print(json.dumps(report, indent=2))
    return 0
