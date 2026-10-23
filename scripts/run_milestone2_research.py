"""Run scalable Milestone 2 research over the Parquet warehouse."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from nse_quant.research.iv_regimes import (
    classify_iv_regimes,
    save_regime_report,
)
from nse_quant.research.iv_surface import (
    build_daily_iv_summary,
    build_iv_surface_report,
    save_reports,
)
from nse_quant.research.parquet_warehouse import ParquetWarehouse
from nse_quant.research.regimes import rolling_percentile
from nse_quant.research.warehouse_validation import validate_warehouse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Milestone 2 IV and RV research.")

    parser.add_argument(
        "--warehouse-dir",
        default="data/exports",
    )
    parser.add_argument(
        "--symbol",
        default="NIFTY",
    )
    parser.add_argument(
        "--rv-csv",
        default="data/research/daily_rv_NIFTY.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="data/research/milestone2",
    )
    parser.add_argument(
        "--min-snapshots",
        type=int,
        default=100,
    )
    parser.add_argument(
        "--min-iv-coverage",
        type=float,
        default=0.80,
    )

    return parser.parse_args()


def load_research_grade_option_streams(
    *,
    warehouse_dir: Path,
    underlying: str,
    min_snapshots: int,
    min_iv_coverage: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    validation = validate_warehouse(
        warehouse_dir,
        underlying=underlying,
        min_snapshots=min_snapshots,
        min_iv_coverage=min_iv_coverage,
    )

    valid = validation[validation["status"] == "ok"].copy()

    if valid.empty:
        return pd.DataFrame(), validation

    warehouse = ParquetWarehouse(warehouse_dir)

    dates = [Path(path).stem.replace("option_stream_", "") for path in valid["file"]]

    frames: list[pd.DataFrame] = []

    for trade_date in dates:
        frame = warehouse.load_option_stream(
            underlying=underlying,
            start_date=trade_date,
            end_date=trade_date,
        )

        if not frame.empty:
            frames.append(frame)

    if not frames:
        return pd.DataFrame(), validation

    return (
        pd.concat(frames, ignore_index=True),
        validation,
    )


def build_rv_regimes(
    rv: pd.DataFrame,
    *,
    underlying: str,
) -> pd.DataFrame:
    frame = rv.copy()

    if "trade_date" not in frame.columns:
        if "trading_date" not in frame.columns:
            raise ValueError("RV file must contain either 'trade_date' or 'trading_date'")

        frame = frame.rename(columns={"trading_date": "trade_date"})

    required = {
        "trade_date",
        "realized_volatility",
    }

    missing = required.difference(frame.columns)

    if missing:
        raise ValueError(f"RV file missing columns: {sorted(missing)}")

    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date

    frame = frame.sort_values("trade_date")

    frame["rv_percentile"] = rolling_percentile(
        frame["realized_volatility"],
        window=252,
    )

    def label(value: float | None) -> str:
        if value is None or pd.isna(value):
            return "UNKNOWN"

        if value >= 80:
            return "HIGH_RV"

        if value <= 20:
            return "LOW_RV"

        return "NORMAL_RV"

    frame["rv_regime"] = frame["rv_percentile"].apply(label)

    frame["underlying"] = underlying

    return frame[
        [
            "trade_date",
            "underlying",
            "realized_volatility",
            "rv_percentile",
            "rv_regime",
        ]
    ]


def main() -> None:
    args = parse_args()

    warehouse_dir = Path(args.warehouse_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    option_stream, validation = load_research_grade_option_streams(
        warehouse_dir=warehouse_dir,
        underlying=args.symbol,
        min_snapshots=args.min_snapshots,
        min_iv_coverage=args.min_iv_coverage,
    )

    validation_path = output_dir / f"warehouse_validation_{args.symbol}.csv"
    validation.to_csv(validation_path, index=False)

    if option_stream.empty:
        print(f"No research-grade option-stream days found. Validation saved to {validation_path}")
        return

    snapshot_report = build_iv_surface_report(
        option_stream,
        underlying=args.symbol,
    )

    daily_iv = build_daily_iv_summary(snapshot_report)

    iv_regimes = classify_iv_regimes(daily_iv)

    snapshot_path, daily_path = save_reports(
        snapshot_report=snapshot_report,
        daily_report=daily_iv,
        output_dir=output_dir,
        underlying=args.symbol,
    )

    regime_path = save_regime_report(
        iv_regimes,
        output_dir=output_dir,
        underlying=args.symbol,
    )

    rv_path = Path(args.rv_csv)

    if rv_path.exists():
        rv = pd.read_csv(rv_path)

        rv_regimes = build_rv_regimes(
            rv,
            underlying=args.symbol,
        )

        rv_regimes_path = output_dir / f"rv_regimes_{args.symbol}.csv"

        rv_regimes.to_csv(
            rv_regimes_path,
            index=False,
        )
    else:
        rv_regimes_path = None

    print("Milestone 2 research complete")
    print(f"Validation: {validation_path}")
    print(f"IV snapshots: {snapshot_path}")
    print(f"IV daily: {daily_path}")
    print(f"IV regimes: {regime_path}")

    if rv_regimes_path:
        print(f"RV regimes: {rv_regimes_path}")


if __name__ == "__main__":
    main()
