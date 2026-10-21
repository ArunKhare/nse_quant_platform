"""Run an iron-condor parameter sweep over Parquet warehouse data."""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import pandas as pd

from nse_quant.core.settings import get_settings
from nse_quant.research.iron_condor_backtest import (
    IronCondorBacktester,
    IronCondorConfig,
    trades_to_frame,
)
from nse_quant.research.parquet_warehouse import (
    ParquetWarehouse,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--underlying",
        default="NIFTY",
    )
    parser.add_argument(
        "--start",
        required=True,
    )
    parser.add_argument(
        "--end",
        required=True,
    )
    parser.add_argument(
        "--warehouse-dir",
        default=None,
    )
    parser.add_argument(
        "--output-dir",
        default="data/backtests",
    )

    parser.add_argument(
        "--short-deltas",
        default="0.10,0.15,0.20,0.25",
    )
    parser.add_argument(
        "--wing-widths",
        default="50,100,150",
    )
    parser.add_argument(
        "--profit-targets",
        default="0.30,0.50,0.70",
    )
    parser.add_argument(
        "--stop-multiples",
        default="1.5,2.0,3.0",
    )

    return parser.parse_args()


def floats(value: str) -> list[float]:
    return [
        float(item)
        for item in value.split(",")
        if item
    ]


def ints(value: str) -> list[int]:
    return [
        int(item)
        for item in value.split(",")
        if item
    ]


def summarize(
    trades: pd.DataFrame,
    config: IronCondorConfig,
) -> dict[str, float | int | str]:
    trade_count = len(trades)

    total_pnl = (
        float(trades["pnl"].sum())
        if trade_count
        else 0.0
    )

    win_rate = (
        float((trades["pnl"] > 0).mean())
        if trade_count
        else 0.0
    )

    avg_pnl = (
        float(trades["pnl"].mean())
        if trade_count
        else 0.0
    )

    equity = trades["pnl"].cumsum()

    running_max = equity.cummax()
    drawdown = equity - running_max
    max_drawdown = (
        float(drawdown.min())
        if trade_count
        else 0.0
    )

    returns = trades["pnl"]
    sharpe = (
        float(
            returns.mean()
            / returns.std()
            * (252 ** 0.5)
        )
        if trade_count > 1
        and returns.std() > 0
        else 0.0
    )

    return {
        "underlying": config.underlying,
        "short_delta": config.short_delta,
        "wing_width": config.wing_width,
        "profit_target_pct": (
            config.profit_target_pct
        ),
        "stop_loss_multiple": (
            config.stop_loss_multiple
        ),
        "trades": trade_count,
        "win_rate": round(win_rate, 4),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(avg_pnl, 2),
        "max_drawdown": round(
            max_drawdown, 2
        ),
        "sharpe": round(sharpe, 4),
    }


def main() -> int:
    args = parse_args()
    settings = get_settings()

    warehouse_dir = (
        args.warehouse_dir
        or settings.storage.parquet_dir
    )

    warehouse = ParquetWarehouse(
        warehouse_dir
    )

    frame = warehouse.load_option_stream(
        underlying=args.underlying,
        start_date=args.start,
        end_date=args.end,
    )

    if frame.empty:
        print(
            "No warehouse data found for "
            "the requested range."
        )
        return 1

    short_deltas = floats(
        args.short_deltas
    )
    wing_widths = ints(
        args.wing_widths
    )
    profit_targets = floats(
        args.profit_targets
    )
    stop_multiples = floats(
        args.stop_multiples
    )

    results: list[
        dict[str, float | int | str]
    ] = []

    combinations = itertools.product(
        short_deltas,
        wing_widths,
        profit_targets,
        stop_multiples,
    )

    for (
        short_delta,
        wing_width,
        profit_target,
        stop_multiple,
    ) in combinations:
        config = IronCondorConfig(
            underlying=args.underlying,
            short_delta=short_delta,
            wing_width=wing_width,
            profit_target_pct=profit_target,
            stop_loss_multiple=stop_multiple,
        )

        backtester = IronCondorBacktester(
            frame=frame,
            config=config,
        )

        trades = trades_to_frame(
            backtester.run()
        )

        results.append(
            summarize(
                trades=trades,
                config=config,
            )
        )

    results_frame = pd.DataFrame(results)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_dir
        / (
            "iron_condor_sweep_"
            f"{args.underlying}_"
            f"{args.start}_{args.end}.csv"
        )
    )

    results_frame.to_csv(
        output_path,
        index=False,
    )

    print(results_frame.to_string(
        index=False
    ))
    print(f"Saved: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())