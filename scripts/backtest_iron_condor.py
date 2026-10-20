"""Run a historical iron-condor backtest from Parquet warehouse data."""

from __future__ import annotations

import argparse
from pathlib import Path

from nse_quant.core.settings import get_settings
from nse_quant.research.iron_condor_backtest import (
    IronCondorBacktester,
    IronCondorConfig,
    trades_to_frame,
)
from nse_quant.research.parquet_warehouse import ParquetWarehouse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest NIFTY iron condors"
    )

    parser.add_argument(
        "--underlying",
        default="NIFTY",
    )

    parser.add_argument(
        "--start",
        required=True,
        help="Start date, YYYY-MM-DD",
    )

    parser.add_argument(
        "--end",
        required=True,
        help="End date, YYYY-MM-DD",
    )

    parser.add_argument(
        "--warehouse-dir",
        default=None,
    )

    parser.add_argument(
        "--short-delta",
        type=float,
        default=0.20,
    )

    parser.add_argument(
        "--wing-width",
        type=int,
        default=100,
    )

    parser.add_argument(
        "--lot-size",
        type=int,
        default=75,
    )

    parser.add_argument(
        "--profit-target",
        type=float,
        default=0.50,
        help="Profit target as a fraction of entry credit",
    )

    parser.add_argument(
        "--stop-multiple",
        type=float,
        default=2.0,
        help="Stop-loss credit multiple",
    )

    parser.add_argument(
        "--output-dir",
        default="data/backtests",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()

    warehouse_dir = (
        args.warehouse_dir
        or settings.storage.parquet_dir
    )

    warehouse = ParquetWarehouse(warehouse_dir)

    frame = warehouse.load_option_stream(
        underlying=args.underlying,
        start_date=args.start,
        end_date=args.end,
    )

    if frame.empty:
        print("No warehouse data found for the requested range.")
        return 1

    config = IronCondorConfig(
        underlying=args.underlying,
        short_delta=args.short_delta,
        wing_width=args.wing_width,
        lot_size=args.lot_size,
        profit_target_pct=args.profit_target,
        stop_loss_multiple=args.stop_multiple,
    )

    backtester = IronCondorBacktester(
        frame=frame,
        config=config,
    )

    trades = backtester.run()
    trades_frame = trades_to_frame(trades)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades_path = (
        output_dir
        / f"iron_condor_{args.underlying}_{args.start}_{args.end}.csv"
    )

    trades_frame.to_csv(trades_path, index=False)

    total_pnl = (
        trades_frame["pnl"].sum()
        if not trades_frame.empty
        else 0.0
    )

    win_rate = (
        (trades_frame["pnl"] > 0).mean()
        if not trades_frame.empty
        else 0.0
    )

    print(
        {
            "trades": len(trades_frame),
            "total_pnl": round(float(total_pnl), 2),
            "win_rate": round(float(win_rate), 4),
            "trades_file": str(trades_path),
        }
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())