"""Bootstrap daily NIFTY ATM IV history from NSE F&O EOD bhavcopy files."""

from __future__ import annotations

import argparse
import zipfile
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

from nse_quant.analytics.implied_volatility import (
    implied_volatility,
    time_to_expiry_years,
)
from nse_quant.core.constants import IST
from nse_quant.core.settings import get_settings
from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build daily NIFTY ATM IV observations from NSE F&O "
            "EOD bhavcopy CSV files."
        )
    )
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--underlying", default="NIFTY")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument(
        "--risk-free-rate",
        type=float,
        default=get_settings().analytics.risk_free_rate,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report ATM IV without writing to the warehouse.",
    )
    return parser.parse_args()




def load_bhavcopy(path: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    with zipfile.ZipFile(path) as archive:
        csv_names = [
            name
            for name in archive.namelist()
            if name.lower().endswith(".csv")
        ]

        if not csv_names:
            raise ValueError(
                f"{path.name}: no CSV files inside ZIP"
            )

        for name in csv_names:
            with archive.open(name) as handle:
                frame = pd.read_csv(handle)

            frame.columns = [
                column.strip() for column in frame.columns
            ]
            frames.append(frame)

    if not frames:
        raise ValueError(f"{path.name}: no readable CSV data")

    return pd.concat(frames, ignore_index=True)


def normalise_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()

    frame.columns = [
        column.strip() for column in frame.columns
    ]

    frame["TradDt"] = pd.to_datetime(
        frame["TradDt"],
        errors="coerce",
    )
    frame["XpryDt"] = pd.to_datetime(
        frame["XpryDt"],
        errors="coerce",
    )
    frame["StrkPric"] = pd.to_numeric(
        frame["StrkPric"],
        errors="coerce",
    )
    frame["ClsPric"] = pd.to_numeric(
        frame["ClsPric"],
        errors="coerce",
    )
    frame["UndrlygPric"] = pd.to_numeric(
        frame["UndrlygPric"],
        errors="coerce",
    )

    frame["TckrSymb"] = (
        frame["TckrSymb"]
        .astype(str)
        .str.strip()
        .str.upper()
    )
    frame["OptnTp"] = (
        frame["OptnTp"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    return frame


def load_all_nifty_udiff(data_dir: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for path in sorted(data_dir.glob("*.zip")):
        print("Reading:", path.name)

        frame = load_bhavcopy(path)
        frame = normalise_frame(frame)

        nifty = frame[frame["TckrSymb"] == "NIFTY"]

        print("NIFTY rows:", len(nifty))

        if not nifty.empty:
            frames.append(nifty)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)

def select_atm_iv(
    frame: pd.DataFrame,
    *,
    trading_date: date,
    spot: float | None,
    risk_free_rate: float,
) -> tuple[date, date, float, float] | None:
    day = frame[
        (frame["TckrSymb"] == "NIFTY")
        & (frame["TradDt"].dt.date == trading_date)
        & (frame["XpryDt"].dt.date > trading_date)
        & frame["StrkPric"].notna()
        & frame["ClsPric"].notna()
    ]

    if day.empty:
        return None

    if spot is None or spot <= 0:
        spot_values = day["UndrlygPric"].dropna()
        if spot_values.empty:
            return None
        spot = float(spot_values.iloc[-1])

    nearest_expiry = day["XpryDt"].min().date()
    day = day[day["XpryDt"].dt.date == nearest_expiry]

    atm_index = day["StrkPric"].sub(spot).abs().idxmin()
    atm_strike = float(day.loc[atm_index, "StrkPric"])
    day = day[day["StrkPric"] == atm_strike]

    expiry_dt = datetime.combine(
        nearest_expiry,
        time(15, 30),
        tzinfo=IST,
    )
    as_of_dt = datetime.combine(
        trading_date,
        time(15, 30),
        tzinfo=IST,
    )

    time_to_expiry = time_to_expiry_years(
        as_of=as_of_dt,
        expiry=expiry_dt,
    )

    ivs: list[float] = []

    for option_type in ("CE", "PE"):
        row = day[day["OptnTp"] == option_type]

        if row.empty:
            continue

        price = float(row.iloc[0]["ClsPric"])

        if price <= 0:
            continue

        iv = implied_volatility(
            option_price=price,
            spot=spot,
            strike=atm_strike,
            time_to_expiry_years=time_to_expiry,
            risk_free_rate=risk_free_rate,
            option_type=option_type,
        )

        if iv is not None:
            ivs.append(iv)

    if not ivs:
        return None

    return (
        trading_date,
        nearest_expiry,
        float(sum(ivs) / len(ivs)),
        spot,
    )

def main() -> int:
    args = parse_args()

    data_dir = Path(args.data_dir)
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)

    store = DuckDBStore()

    try:
        spot_row = store.conn.execute(
            """
            SELECT CAST(ts AS DATE), close
            FROM spot_candles
            WHERE symbol = ?
              AND interval = 'day'
              AND CAST(ts AS DATE) BETWEEN ? AND ?
            ORDER BY ts
            """,
            [args.underlying, start_date, end_date],
        ).fetchall()

        if not spot_row:
            print("No daily NIFTY closes found.")
            return 1

        written = 0
        skipped = 0
        all_nifty = load_all_nifty_udiff(data_dir)

        print(f"NIFTY UDiFF rows loaded: {len(all_nifty)}")

        if all_nifty.empty:
            print("No NIFTY rows found in bhavcopy files.")
            return 1

        for trading_date, spot in spot_row:
            day = all_nifty[
                (all_nifty["TckrSymb"] == "NIFTY")
                & (all_nifty["TradDt"].dt.date == trading_date)
            ]

            if day.empty:
                print(f"{trading_date}: SKIP no_nifty_rows")
                skipped += 1
                continue

            valid_day = day[
                (day["XpryDt"].dt.date > trading_date)
                & day["StrkPric"].notna()
                & day["ClsPric"].notna()
                & (day["ClsPric"] > 0)
            ]

            if valid_day.empty:
                print(
                    f"{trading_date}: SKIP no_valid_future_expiry_or_price"
                )
                skipped += 1
                continue

            observation = select_atm_iv(
                all_nifty,
                trading_date=trading_date,
                spot=float(spot),
                risk_free_rate=args.risk_free_rate,
            )

            if observation is None:
                print(
                    f"{trading_date}: SKIP iv_calculation_failed "
                    f"spot={spot}"
                )
                skipped += 1
                continue

            observed_date, expiry, iv, spot_price = observation

            print(
                f"{observed_date}: expiry={expiry} "
                f"atm_iv={iv:.4f} spot={spot_price:.2f}"
            )

            if args.dry_run:
                continue

            written += store.write_underlying_iv_observation(
                ts=datetime.combine(
                    observed_date,
                    time(15, 30),
                    tzinfo=IST,
                ),
                underlying=args.underlying,
                expiry=expiry,
                iv=iv,
                spot=spot_price,
                source="nse_eod_bhavcopy_bootstrap",
            )

        print(
            f"Bootstrap complete: written={written}, skipped={skipped}"
        )
        return 0

    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())