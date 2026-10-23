"""Run a historical iron-condor backtest from Parquet warehouse data."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from nse_quant.core.settings import get_settings
from nse_quant.research.iron_condor_backtest import (
    IronCondorBacktester,
    IronCondorConfig,
    trades_to_frame,
)
from nse_quant.research.parquet_warehouse import ParquetWarehouse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest NIFTY iron condors")

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

    parser.add_argument(
        "--contracts",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--slippage-per-leg",
        type=float,
        default=0.50,
    )

    parser.add_argument(
        "--brokerage-per-lot",
        type=float,
        default=20.0,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()

    warehouse_dir = args.warehouse_dir or settings.storage.parquet_dir

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
        contracts=args.contracts,
        slippage_per_leg=args.slippage_per_leg,
        brokerage_per_lot=args.brokerage_per_lot,
        profit_target_pct=args.profit_target,
        stop_loss_multiple=args.stop_multiple,
    )

    backtester = IronCondorBacktester(
        frame=frame,
        config=config,
    )

    trades = backtester.run()
    print(backtester.diagnostics.as_dict())
    trades_frame = trades_to_frame(trades)

    rv_regimes_path = Path("data/research/milestone2/rv_regimes_NIFTY.csv")

    iv_regimes_path = Path("data/research/milestone2/iv_regimes_NIFTY.csv")

    if rv_regimes_path.exists():
        rv_regimes = pd.read_csv(rv_regimes_path)

        rv_regimes["trade_date"] = pd.to_datetime(rv_regimes["trade_date"]).dt.date

        trades_frame["trade_date"] = pd.to_datetime(
            trades_frame["exit_ts"],
            utc=True,
        ).dt.date

        trades_frame = trades_frame.merge(
            rv_regimes[
                [
                    "trade_date",
                    "realized_volatility",
                    "rv_percentile",
                    "rv_regime",
                ]
            ],
            on="trade_date",
            how="left",
        )

    if iv_regimes_path.exists():
        iv_regimes = pd.read_csv(iv_regimes_path)

        iv_regimes["trade_date"] = pd.to_datetime(iv_regimes["trade_date"]).dt.date

        trades_frame = trades_frame.merge(
            iv_regimes[
                [
                    "trade_date",
                    "iv_level",
                    "iv_term_regime",
                    "iv_skew_regime",
                    "iv_regime",
                ]
            ],
            on="trade_date",
            how="left",
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades_path = output_dir / f"iron_condor_{args.underlying}_{args.start}_{args.end}.csv"

    trades_frame.to_csv(trades_path, index=False)

    if not trades_frame.empty:
        trades_frame["trade_date"] = pd.to_datetime(
            trades_frame["exit_ts"],
            utc=True,
        ).dt.date

        daily = trades_frame.groupby("trade_date", as_index=False).agg(
            pnl=("pnl", "sum"),
            trades=("pnl", "count"),
        )

        daily["capital_base"] = 100000.0
        daily["daily_return"] = daily["pnl"] / daily["capital_base"]

        returns_path = (
            output_dir / f"iron_condor_daily_returns_{args.underlying}_{args.start}_{args.end}.csv"
        )

        daily.to_csv(returns_path, index=False)

        print(
            {
                "daily_returns_file": str(returns_path),
                "trading_days": len(daily),
            }
        )

    total_pnl = trades_frame["pnl"].sum() if not trades_frame.empty else 0.0

    win_rate = (trades_frame["pnl"] > 0).mean() if not trades_frame.empty else 0.0

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
