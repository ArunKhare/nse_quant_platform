from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import quantstats as qs


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
        default="data/research/backtests",
        help="Directory containing backtest run outputs.",
    )
    parser.add_argument(
        "--risk-free-rate",
        type=float,
        default=0.0,
        help="Annualized risk-free rate used by QuantStats.",
    )

    return parser.parse_args()


def load_equity_curve(path: Path) -> pd.Series:
    frame = pd.read_csv(path)
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame = frame.sort_values("ts").drop_duplicates(subset="ts", keep="last")
    frame = frame.set_index("ts")

    equity = frame["equity"].astype(float)

    if equity.empty:
        raise ValueError(f"Equity curve is empty: {path}")

    return equity


def equity_to_returns(equity: pd.Series) -> pd.Series:
    returns = equity.pct_change().fillna(0.0)
    return returns.iloc[1:] if len(returns) > 1 else returns


def load_trade_stats(path: Path) -> dict[str, float | int | None]:
    if not path.exists():
        return {
            "trade_count": 0,
            "win_rate": None,
            "profit_factor": None,
        }

    trades = pd.read_csv(path)

    if trades.empty or "realized_pnl" not in trades.columns:
        return {
            "trade_count": 0,
            "win_rate": None,
            "profit_factor": None,
        }

    pnl = pd.to_numeric(trades["realized_pnl"], errors="coerce").dropna()
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    gross_profit = float(wins.sum())
    gross_loss = abs(float(losses.sum()))

    return {
        "trade_count": int(len(pnl)),
        "win_rate": float(len(wins) / len(pnl)) if len(pnl) else None,
        "profit_factor": (
            gross_profit / gross_loss
            if gross_loss > 0
            else (None if gross_profit == 0 else float("inf"))
        ),
    }


def calculate_summary(
    equity: pd.Series,
    returns: pd.Series,
    trade_stats: dict[str, float | int | None],
    risk_free_rate: float,
) -> dict[str, float | int | str | None]:
    elapsed_years = max(
        (equity.index[-1] - equity.index[0]).total_seconds() / (365.25 * 24 * 60 * 60),
        1.0 / (365.25 * 24 * 60 * 60),
    )
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1 / elapsed_years) - 1.0)

    def metric(func, default=None):
        try:
            value = func()
            if pd.isna(value):
                return default
            return float(value)
        except (ValueError, TypeError, ZeroDivisionError):
            return default

    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe_ratio": metric(
            lambda: qs.stats.sharpe(
                returns,
                rf=risk_free_rate,
                periods=252,
                annualize=True,
            ),
        ),
        "sortino_ratio": metric(
            lambda: qs.stats.sortino(
                returns,
                rf=risk_free_rate,
                periods=252,
                annualize=True,
            ),
        ),
        "max_drawdown": metric(lambda: qs.stats.max_drawdown(returns)),
        "volatility": metric(
            lambda: qs.stats.volatility(returns, periods=252, annualize=True),
        ),
        **trade_stats,
    }


def main() -> None:
    args = parse_args()

    run_dir = Path(args.backtest_dir) / args.run_id
    equity_path = run_dir / "equity_curve.csv"
    trades_path = run_dir / "trades.csv"

    if not equity_path.exists():
        raise FileNotFoundError(f"Equity curve not found: {equity_path}")

    equity = load_equity_curve(equity_path)
    returns = equity_to_returns(equity)
    trade_stats = load_trade_stats(trades_path)

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

    report_path = run_dir / "quantstats_report.html"
    summary_path = run_dir / "performance_summary.json"

    qs.reports.html(
        returns,
        output=str(report_path),
        title=f"NSE Quant Backtest - {args.run_id}",
        download_filename=str(report_path.name),
    )

    summary_path.write_text(
        json.dumps(summary_payload, indent=2, default=str),
        encoding="utf-8",
    )

    print("Backtest report generated")
    print(f"Equity points: {len(equity)}")
    print(f"Report: {report_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
