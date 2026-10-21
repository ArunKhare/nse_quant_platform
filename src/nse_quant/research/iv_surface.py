"""IV surface and term-structure research utilities."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {
    "ts",
    "underlying",
    "expiry",
    "strike",
    "option_type",
    "ltp",
    "spot",
    "iv",
    "delta",
}


def build_iv_surface_report(
    frame: pd.DataFrame,
    *,
    underlying: str,
) -> pd.DataFrame:
    """Build snapshot-level IV surface and term-structure metrics."""
    if frame.empty:
        return pd.DataFrame()

    missing = REQUIRED_COLUMNS.difference(frame.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    frame = frame.copy()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame["expiry"] = pd.to_datetime(frame["expiry"]).dt.date
    frame["trade_date"] = frame["ts"].dt.date

    frame = frame[
        (frame["underlying"] == underlying)
        & frame["iv"].notna()
        & frame["delta"].notna()
        & (frame["ltp"] > 0)
    ]

    if frame.empty:
        return pd.DataFrame()

    reports: list[dict[str, object]] = []

    for ts, snapshot in frame.groupby("ts"):
        expiries = sorted(snapshot["expiry"].unique())

        if len(expiries) < 2:
            continue

        for near_expiry, next_expiry in pairwise(expiries):
            near = snapshot[snapshot["expiry"] == near_expiry]
            next_expiry_frame = snapshot[
            snapshot["expiry"] == next_expiry
            ]

            spot = float(near["spot"].iloc[0])

            near_atm = _atm_iv(near, spot)
            next_atm = _atm_iv(next_expiry_frame, spot)

            if near_atm is None or next_atm is None:
                continue

            reports.append(
                {
                    "ts": ts,
                    "trade_date": ts.date(),
                    "underlying": underlying,
                    "spot": spot,
                    "near_expiry": near_expiry,
                    "next_expiry": next_expiry,
                    "tenor_pair": (
                        f"{near_expiry}_to_{next_expiry}"
                    ),
                    "atm_iv_near": near_atm,
                    "atm_iv_next": next_atm,
                    "term_structure": next_atm - near_atm,
                    "put_call_skew": _skew(near, spot),
                    "risk_reversal_25d":  _risk_reversal(near),
                    "butterfly_25d": _butterfly(near),
                }
            )
    if not reports:
        return pd.DataFrame(
            columns=[
                "ts",
                "trade_date",
                "underlying",
                "spot",
                "near_expiry",
                "next_expiry",
                "tenor_pair",
                "atm_iv_near",
                "atm_iv_next",
                "term_structure",
                "put_call_skew",
                "risk_reversal_25d",
                "butterfly_25d",
            ]
        )
    return pd.DataFrame(reports).sort_values("ts")


def build_daily_iv_summary(
    snapshot_report: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate snapshot-level IV metrics into daily medians."""
    if snapshot_report.empty:
        return pd.DataFrame()

    return (
        snapshot_report
        .groupby("trade_date", as_index=False)
        .agg(
            underlying=("underlying", "first"),
            median_spot=("spot", "median"),
            median_atm_iv_near=("atm_iv_near", "median"),
            median_atm_iv_next=("atm_iv_next", "median"),
            median_term_structure=("term_structure", "median"),
            median_put_call_skew=("put_call_skew", "median"),
            median_risk_reversal=("risk_reversal_25d", "median"),
            median_butterfly=("butterfly_25d", "median"),
            snapshots=("ts", "nunique"),
        )
    )


def _atm_iv(
    snapshot: pd.DataFrame,
    spot: float,
) -> float | None:
    valid = snapshot[
        snapshot["iv"].notna()
        & (snapshot["ltp"] > 0)
    ]

    if valid.empty:
        return None

    atm_strike = valid.iloc[
        (valid["strike"] - spot).abs().argmin()
    ]["strike"]

    atm_rows = valid[
        valid["strike"] == atm_strike
    ]

    return float(atm_rows["iv"].mean())


def _skew(
    snapshot: pd.DataFrame,
    spot: float,
) -> float | None:
    puts = snapshot[snapshot["option_type"] == "PE"]
    calls = snapshot[snapshot["option_type"] == "CE"]

    if puts.empty or calls.empty:
        return None

    otm_puts = puts[puts["strike"] < spot]
    otm_calls = calls[calls["strike"] > spot]

    if otm_puts.empty or otm_calls.empty:
        return None

    put_iv = otm_puts.iloc[
        (otm_puts["strike"] - spot).abs().argmin()
    ]["iv"]

    call_iv = otm_calls.iloc[
        (otm_calls["strike"] - spot).abs().argmin()
    ]["iv"]

    if pd.isna(put_iv) or pd.isna(call_iv):
        return None

    return float(put_iv - call_iv)


def _risk_reversal(
    snapshot: pd.DataFrame,
) -> float | None:
    calls = snapshot[
        (snapshot["option_type"] == "CE")
        & snapshot["delta"].notna()
    ]

    puts = snapshot[
        (snapshot["option_type"] == "PE")
        & snapshot["delta"].notna()
    ]

    if calls.empty or puts.empty:
        return None

    calls = calls.copy()
    puts = puts.copy()

    calls["abs_delta"] = calls["delta"].abs()
    puts["abs_delta"] = puts["delta"].abs()

    call_25 = calls.iloc[
        (calls["abs_delta"] - 0.25).abs().argmin()
    ]

    put_25 = puts.iloc[
        (puts["abs_delta"] - 0.25).abs().argmin()
    ]

    if pd.isna(call_25["iv"]) or pd.isna(put_25["iv"]):
        return None

    return float(call_25["iv"] - put_25["iv"])


def _butterfly(
    snapshot: pd.DataFrame,
) -> float | None:
    calls = snapshot[
        (snapshot["option_type"] == "CE")
        & snapshot["delta"].notna()
    ].copy()

    if calls.empty:
        return None

    calls["abs_delta"] = calls["delta"].abs()

    call_25 = calls.iloc[
        (calls["abs_delta"] - 0.25).abs().argmin()
    ]

    atm = calls.iloc[
        (calls["abs_delta"] - 0.50).abs().argmin()
    ]

    if pd.isna(call_25["iv"]) or pd.isna(atm["iv"]):
        return None

    return float(
        2.0 * atm["iv"]
        - call_25["iv"]
        - call_25["iv"]
    )


def save_reports(
    *,
    snapshot_report: pd.DataFrame,
    daily_report: pd.DataFrame,
    output_dir: str | Path,
    underlying: str,
) -> tuple[Path, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    snapshot_path = (
        output_path
        / f"iv_surface_snapshots_{underlying}.csv"
    )
    daily_path = (
        output_path
        / f"iv_surface_daily_{underlying}.csv"
    )

    snapshot_report.to_csv(snapshot_path, index=False)
    daily_report.to_csv(daily_path, index=False)

    return snapshot_path, daily_path

def build_single_expiry_iv_report(
    frame: pd.DataFrame,
    *,
    underlying: str,
) -> pd.DataFrame:
    """Build ATM IV, skew, risk reversal, and butterfly metrics."""

    if frame.empty:
        return pd.DataFrame()

    required = {
        "ts",
        "underlying",
        "expiry",
        "strike",
        "option_type",
        "ltp",
        "spot",
        "iv",
        "delta",
    }

    missing = required.difference(frame.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    frame = frame.copy()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame["expiry"] = pd.to_datetime(
        frame["expiry"]
    ).dt.date

    frame = frame[
        (frame["underlying"] == underlying)
        & frame["iv"].notna()
        & (frame["ltp"] > 0)
    ].copy()

    frame["time_to_expiry"] = frame.apply(
        lambda row: _time_to_expiry_years(
            row["ts"],
            row["expiry"],
        ),
        axis=1,
    )

    frame["delta"] = frame.apply(
        lambda row: (
            row["delta"]
            if pd.notna(row["delta"])
            else black_scholes_delta(
                spot=row["spot"],
                strike=row["strike"],
                iv=row["iv"],
                time_to_expiry=row["time_to_expiry"],
                option_type=row["option_type"],
            )
        ),
        axis=1,
    )

    frame = frame[frame["delta"].notna()]

    reports: list[dict[str, object]] = []

    for ts, snapshot in frame.groupby("ts"):
        spot = float(snapshot["spot"].iloc[0])
        expiry = snapshot["expiry"].iloc[0]

        atm_iv = _atm_iv(snapshot, spot)
        skew = _skew(snapshot, spot)
        risk_reversal = _risk_reversal(snapshot)
        butterfly = _butterfly(snapshot)

        reports.append(
            {
                "ts": ts,
                "trade_date": ts.date(),
                "underlying": underlying,
                "expiry": expiry,
                "spot": spot,
                "atm_iv": atm_iv,
                "put_call_skew": skew,
                "risk_reversal_25d": risk_reversal,
                "butterfly_25d": butterfly,
            }
        )

    return pd.DataFrame(reports).sort_values("ts")


import numpy as np
from scipy.stats import norm

RISK_FREE_RATE = 0.065


def _time_to_expiry_years(
    ts: pd.Timestamp,
    expiry: object,
) -> float:
    expiry_ts = pd.Timestamp(expiry)

    expiry_time = (
        expiry_ts
        + pd.Timedelta(hours=15, minutes=30)
    )

    expiry_time = expiry_time.tz_localize(
        "Asia/Kolkata"
    )

    observation_time = pd.Timestamp(ts).tz_convert(
        "Asia/Kolkata"
    )

    seconds = (
        expiry_time - observation_time
    ).total_seconds()

    return max(
        seconds / (365.0 * 24.0 * 60.0 * 60.0),
        1e-8,
    )


def black_scholes_delta(
    *,
    spot: float,
    strike: float,
    iv: float,
    time_to_expiry: float,
    option_type: str,
    risk_free_rate: float = RISK_FREE_RATE,
) -> float:
    if spot <= 0 or strike <= 0 or iv <= 0:
        return float("nan")

    d1 = (
        np.log(spot / strike)
        + (
            risk_free_rate
            + 0.5 * iv * iv
        ) * time_to_expiry
    ) / (
        iv * np.sqrt(time_to_expiry)
    )

    if option_type == "CE":
        return float(norm.cdf(d1))

    if option_type == "PE":
        return float(norm.cdf(d1) - 1.0)

    return float("nan")