r"""generate Backtest Quant Report
cmd example : python scripts\generate_backtest_report.py --run-id 2026-10-25 --risk-free-rate 0.7
Before:  create the latest backtest report with
cmd example : uv run python scripts/run_backtest.py `
  --start-date 2026-10-21 `
  --end-date 2026-10-23 `
  --run-id 2026-10-21_2026-10-23
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import quantstats as qs

from nse_quant.research.backtest_reporting import (
    calculate_summary,
    equity_to_returns,
    load_walk_forward_equity,
    load_walk_forward_trade_stats,
)

print("GENERATING BACKTEST QNANT REPORT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a QuantStats report for a completed backtest run.",
    )

    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional explicit backtest run ID. Defaults to today's date.",
    )
    parser.add_argument(
        "--backtest-dir",
        default=Path("data/research/backtests"),
        help="Directory containing backtest run outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/research/reports"),
        help="Directory where the QuantStats report and summary JSON are written",
    )
    parser.add_argument(
        "--risk-free-rate",
        type=float,
        default=0.0,
        help="Annualized risk-free rate used by QuantStats.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("PARSING ARGS")
    backtest_dir = Path(args.backtest_dir)
    output_dir = Path(args.output_dir) / args.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    print(backtest_dir)
    print(output_dir)
    equity = load_walk_forward_equity(
        run_id=args.run_id,
        backtest_dir=backtest_dir,
    )

    if equity.empty:
        raise ValueError(f"No equity observations found for {args.run_id!r}")

    returns = equity_to_returns(equity)

    trade_stats = load_walk_forward_trade_stats(
        run_id=args.run_id,
        backtest_dir=backtest_dir,
    )

    summary = calculate_summary(
        equity=equity,
        returns=returns,
        trade_stats=trade_stats,
        risk_free_rate=args.risk_free_rate,
    )

    summary_payload = {
        "run_id": args.run_id,
        "equity_points": int(len(equity)),
        "start_ts": equity.index[0].isoformat(),
        "end_ts": equity.index[-1].isoformat(),
        "initial_equity": float(equity.iloc[0]),
        "final_equity": float(equity.iloc[-1]),
        **summary,
    }

    report_path = output_dir / "quantstats_report.html"
    summary_path = output_dir / "performance_summary.json"

    try:
        qs.reports.html(
            returns,
            output=str(report_path),
            title=f"NSE Quant Walk-Forward - {args.run_id}",
            download_filename=report_path.name,
        )
    except Exception as exc:
        print("QUANTSTATS FAILED")
        print(type(exc).__name__, exc)
        raise

    summary_path.write_text(
        json.dumps(summary_payload, indent=2, default=str),
        encoding="utf-8",
    )

    print("-" * 75)
    print(f"Equity points: {len(equity)}")
    print(f"Report: {report_path}")
    print(f"Summary: {summary_path}")
    print("-" * 75)


if __name__ == "__main__":
    main()
