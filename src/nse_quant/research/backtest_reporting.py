from pathlib import Path

import pandas as pd
import quantstats as qs


def load_walk_forward_equity(
    *,
    run_id: str,
    backtest_dir: Path | str,
) -> pd.DataFrame:
    backtest_dir = Path(backtest_dir)
    pattern = f"{run_id}_fold*_test"

    fold_dirs = sorted(backtest_dir.glob(pattern))

    if not fold_dirs:
        raise FileNotFoundError(
            f"No walk-forward fold directories found for {run_id!r} in {backtest_dir}"
        )

    frames = []

    for fold_dir in fold_dirs:
        equity_path = fold_dir / "equity_curve.csv"

        if not equity_path.exists():
            raise FileNotFoundError(f"Missing equity curve: {equity_path}")

        frame = pd.read_csv(equity_path)
        frame["fold_dir"] = fold_dir.name
        frames.append(frame)

    equity = pd.concat(frames, ignore_index=True)

    timestamp_column = next(
        column for column in ("timestamp", "ts", "date", "datetime") if column in equity.columns
    )

    equity_column = next(
        column
        for column in ("equity", "equity_value", "portfolio_value", "nav")
        if column in equity.columns
    )

    equity[timestamp_column] = pd.to_datetime(equity[timestamp_column])

    equity_series = (
        equity[[timestamp_column, equity_column]]
        .sort_values(timestamp_column)
        .drop_duplicates(subset=[timestamp_column], keep="last")
        .set_index(timestamp_column)[equity_column]
        .astype(float)
        .sort_index()
    )

    return equity_series


def equity_to_returns(equity: pd.Series) -> pd.Series:
    returns = equity.pct_change().fillna(0.0)
    return returns.iloc[1:] if len(returns) > 1 else returns


def load_walk_forward_trade_stats(
    *,
    run_id: str,
    backtest_dir: Path | str,
) -> pd.DataFrame | None:
    backtest_dir = Path(backtest_dir)

    fold_dirs = sorted(backtest_dir.glob(f"{run_id}_fold*_test"))
    trade_frames = []

    for fold_dir in fold_dirs:
        trades_path = fold_dir / "trades.csv"

        if not trades_path.exists():
            continue

        if trades_path.stat().st_size == 0:
            print(f"Skipping empty trades file: {trades_path}")
            continue

        try:
            frame = pd.read_csv(trades_path)
        except pd.errors.EmptyDataError:
            print(f"Skipping empty trades file: {trades_path}")
            continue

        if frame.empty:
            print(f"Skipping trades file with no rows: {trades_path}")
            continue

        frame["fold_dir"] = fold_dir.name
        trade_frames.append(frame)

    if not trade_frames:
        return None

    return pd.concat(trade_frames, ignore_index=True)


def calculate_summary(
    equity: pd.Series,
    returns: pd.Series,
    trade_stats: pd.DataFrame | None,
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

    trade_summary: dict[str, float | int | None]
    if trade_stats is None or trade_stats.empty:
        trade_summary = {
            "trade_count": 0,
            "win_rate": None,
            "profit_factor": None,
        }
    else:
        pnl_column = next(
            (
                column
                for column in ("realized_pnl", "pnl", "net_pnl")
                if column in trade_stats.columns
            ),
            None,
        )

        if pnl_column is None:
            trade_summary = {
                "trade_count": int(len(trade_stats)),
                "win_rate": None,
                "profit_factor": None,
            }
        else:
            pnl = pd.to_numeric(trade_stats[pnl_column], errors="coerce").dropna()
            wins = pnl[pnl > 0]
            losses = pnl[pnl < 0]

            trade_summary = {
                "trade_count": int(len(pnl)),
                "win_rate": float(len(wins) / len(pnl)) if len(pnl) else None,
                "profit_factor": (
                    float(wins.sum() / abs(losses.sum()))
                    if not losses.empty and losses.sum() != 0
                    else None
                ),
            }

    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe_ratio": metric(
            lambda: qs.stats.sharpe(
                returns,
                rf=risk_free_rate,
                periods=252,
                annualize=True,
            )
        ),
        "sortino_ratio": metric(
            lambda: qs.stats.sortino(
                returns,
                rf=risk_free_rate,
                periods=252,
                annualize=True,
            )
        ),
        "max_drawdown": metric(lambda: qs.stats.max_drawdown(returns)),
        "volatility": metric(lambda: qs.stats.volatility(returns, periods=252, annualize=True)),
        **trade_summary,
    }


def compare_experiments(
    registry_path: Path,
    *,
    min_trades: int,
    output_path: Path,
) -> pd.DataFrame:
    if not registry_path.exists():
        raise FileNotFoundError(f"Experiment registry not found: {registry_path}")

    registry = pd.read_csv(registry_path)

    required_columns = {
        "run_id",
        "start_date",
        "end_date",
        "out_of_sample_trades",
        "out_of_sample_pnl",
        "research_grade_status",
        "min_iv_rank",
        "max_spread_pct",
    }

    missing = required_columns - set(registry.columns)
    if missing:
        raise ValueError(f"Registry is missing required columns: {sorted(missing)}")

    eligible = registry[registry["out_of_sample_trades"] >= min_trades].copy()

    eligible = eligible.sort_values(
        ["out_of_sample_pnl", "out_of_sample_trades"],
        ascending=[False, False],
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    eligible.to_csv(output_path, index=False)

    return eligible
