from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import quantstats as qs

REQUIRED_EQUITY_COLUMNS = {"ts", "equity"}


def load_equity_curve(path: Path) -> pd.Series:
    frame = pd.read_csv(path)
    missing = REQUIRED_EQUITY_COLUMNS.difference(frame.columns)

    if missing:
        raise ValueError(
            f"Equity curve is missing required columns: {sorted(missing)}",
        )

    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame = frame.sort_values("ts").drop_duplicates(subset="ts", keep="last")

    if frame.empty:
        raise ValueError(f"Equity curve is empty: {path}")

    equity = frame.set_index("ts")["equity"].astype(float)

    if (equity <= 0).any():
        raise ValueError("Equity curve must contain only positive equity values")

    return equity


def equity_to_returns(equity: pd.Series) -> pd.Series:
    returns = equity.pct_change().dropna()
    return returns


def load_trade_performance(path: Path) -> dict[str, int | float | None]:
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


def _safe_metric(func) -> float | None:
    try:
        value = func()
    except (ValueError, TypeError, ZeroDivisionError):
        return None

    if value is None or pd.isna(value):
        return None

    return float(value)


def calculate_performance_summary(
    equity: pd.Series,
    returns: pd.Series,
    trade_performance: dict[str, int | float | None],
    risk_free_rate: float = 0.0,
) -> dict[str, int | float | str | None]:
    elapsed_seconds = (equity.index[-1] - equity.index[0]).total_seconds()
    elapsed_years = elapsed_seconds / (365.25 * 24 * 60 * 60)

    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)

    # CAGR is not meaningful for sub-daily research windows and can overflow
    # when the annualization exponent becomes very large.
    cagr: float | None = None

    if elapsed_years >= 1.0 / 365.25:
        growth_factor = equity.iloc[-1] / equity.iloc[0]

        if growth_factor > 0:
            cagr = float(growth_factor ** (1 / elapsed_years) - 1.0)

    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe_ratio": _safe_metric(
            lambda: qs.stats.sharpe(
                returns,
                rf=risk_free_rate,
                periods=252,
                annualize=True,
            ),
        ),
        "sortino_ratio": _safe_metric(
            lambda: qs.stats.sortino(
                returns,
                rf=risk_free_rate,
                periods=252,
                annualize=True,
            ),
        ),
        "max_drawdown": _safe_metric(
            lambda: qs.stats.max_drawdown(returns),
        ),
        "volatility": _safe_metric(
            lambda: qs.stats.volatility(
                returns,
                periods=252,
                annualize=True,
            ),
        ),
        **trade_performance,
    }


def generate_backtest_report(
    run_dir: Path,
    risk_free_rate: float = 0.0,
) -> tuple[Path, Path]:
    equity_path = run_dir / "equity_curve.csv"
    trades_path = run_dir / "trades.csv"

    if not equity_path.exists():
        raise FileNotFoundError(f"Equity curve not found: {equity_path}")

    equity = load_equity_curve(equity_path)
    returns = equity_to_returns(equity)
    trade_performance = load_trade_performance(trades_path)

    summary = calculate_performance_summary(
        equity=equity,
        returns=returns,
        trade_performance=trade_performance,
        risk_free_rate=risk_free_rate,
    )

    report_path = run_dir / "quantstats_report.html"
    summary_path = run_dir / "performance_summary.json"

    qs.reports.html(
        returns,
        output=str(report_path),
        title=f"NSE Quant Backtest - {run_dir.name}",
        download_filename=report_path.name,
    )

    payload = {
        "run_id": run_dir.name,
        "equity_points": int(len(equity)),
        "start_ts": equity.index[0].isoformat(),
        "end_ts": equity.index[-1].isoformat(),
        "initial_equity": float(equity.iloc[0]),
        "final_equity": float(equity.iloc[-1]),
        **summary,
    }

    summary_path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )

    return report_path, summary_path
