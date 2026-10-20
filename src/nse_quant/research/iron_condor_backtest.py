"""Historical iron-condor backtester using partitioned Parquet data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import pandas as pd


@dataclass(frozen=True)
class IronCondorConfig:
    underlying: str = "NIFTY"
    short_delta: float = 0.20
    wing_width: int = 100
    entry_time: time = time(9, 20)
    exit_time: time = time(15, 15)
    profit_target_pct: float = 0.50
    stop_loss_multiple: float = 2.0
    lot_size: int = 75


@dataclass
class BacktestTrade:
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    expiry: date
    spot_entry: float
    spot_exit: float
    credit_entry: float
    credit_exit: float
    pnl: float
    exit_reason: str


class IronCondorBacktester:
    """Backtests cash-settled index iron condors from option_stream data."""

    def __init__(
        self,
        frame: pd.DataFrame,
        config: IronCondorConfig | None = None,
    ) -> None:
        if frame.empty:
            raise ValueError("Cannot backtest an empty option-stream frame")

        self.frame = frame.copy()
        self.config = config or IronCondorConfig()

        required = {
            "ts",
            "underlying",
            "expiry",
            "strike",
            "option_type",
            "ltp",
            "spot",
            "delta",
        }

        missing = required.difference(self.frame.columns)

        if missing:
            raise ValueError(
                f"Missing required option-stream columns: {sorted(missing)}"
            )

        self.frame["ts"] = pd.to_datetime(
            self.frame["ts"],
            utc=True,
        )
        self.frame["expiry"] = pd.to_datetime(
            self.frame["expiry"]
        ).dt.date
        self.frame["trade_date"] = self.frame["ts"].dt.date

    def run(self) -> list[BacktestTrade]:
        trades: list[BacktestTrade] = []

        for trade_date, day_frame in self.frame.groupby("trade_date"):
            trade = self._backtest_day(
                trade_date=trade_date,
                day_frame=day_frame,
            )

            if trade is not None:
                trades.append(trade)

        return trades

    def _backtest_day(
        self,
        *,
        trade_date: date,
        day_frame: pd.DataFrame,
    ) -> BacktestTrade | None:
        entry_frame = day_frame[
            (day_frame["ts"].dt.time >= self.config.entry_time)
        ]

        if entry_frame.empty:
            return None

        entry_ts = entry_frame["ts"].min()
        entry_snapshot = entry_frame[
            entry_frame["ts"] == entry_ts
        ]

        expiry = self._select_expiry(entry_snapshot)

        if expiry is None:
            return None

        expiry_snapshot = entry_snapshot[
            entry_snapshot["expiry"] == expiry
        ]

        legs = self._select_legs(expiry_snapshot)

        if legs is None:
            return None

        credit_entry = self._credit(legs)
        spot_entry = float(expiry_snapshot["spot"].iloc[0])

        exit_result = self._simulate_exit(
            day_frame=day_frame,
            expiry=expiry,
            legs=legs,
            entry_ts=entry_ts,
            credit_entry=credit_entry,
            spot_entry=spot_entry,
        )

        if exit_result is None:
            return None

        exit_ts, exit_snapshot, exit_reason = exit_result

        exit_legs = self._match_exit_legs(
            exit_snapshot=exit_snapshot,
            legs=legs,
        )

        if exit_legs is None:
            return None

        credit_exit = self._credit(exit_legs)
        spot_exit = float(exit_snapshot["spot"].iloc[0])

        pnl = (credit_entry - credit_exit) * self.config.lot_size

        return BacktestTrade(
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            expiry=expiry,
            spot_entry=spot_entry,
            spot_exit=spot_exit,
            credit_entry=credit_entry,
            credit_exit=credit_exit,
            pnl=pnl,
            exit_reason=exit_reason,
        )

    def _select_expiry(
        self,
        snapshot: pd.DataFrame,
    ) -> date | None:
        expiries = sorted(snapshot["expiry"].unique())

        return expiries[0] if expiries else None

    def _select_legs(
        self,
        snapshot: pd.DataFrame,
    ) -> dict[str, pd.Series] | None:

        if "spot" not in snapshot.columns:
            raise ValueError("snapshot must contain a 'spot' column")

        puts = snapshot[
            (snapshot["option_type"] == "PE")
            & snapshot["delta"].notna()
            & (snapshot["delta"] < 0)
        ].copy()

        calls = snapshot[
            (snapshot["option_type"] == "CE")
            & snapshot["delta"].notna()
            & (snapshot["delta"] > 0)
        ].copy()

        if puts.empty or calls.empty:
            return None

        puts["abs_delta"] = puts["delta"].abs()
        calls["abs_delta"] = calls["delta"].abs()

        short_put = puts.iloc[
            (puts["abs_delta"] - self.config.short_delta)
            .abs()
            .argmin()
        ]

        short_call = calls.iloc[
            (calls["abs_delta"] - self.config.short_delta)
            .abs()
            .argmin()
        ]

        long_put = puts[
            puts["strike"]
            == short_put["strike"] - self.config.wing_width
        ]

        long_call = calls[
            calls["strike"]
            == short_call["strike"] + self.config.wing_width
        ]

        if long_put.empty or long_call.empty:
            return None

        return {
            "short_put": short_put.iloc[0],
            "long_put": long_put.iloc[0],
            "short_call": short_call.iloc[0],
            "long_call": long_call.iloc[0],
        }

    @staticmethod
    def _credit(legs: dict[str, pd.Series]) -> float:
        return float(
            legs["short_put"]["ltp"]
            + legs["short_call"]["ltp"]
            - legs["long_put"]["ltp"]
            - legs["long_call"]["ltp"]
        )

    def _simulate_exit(
        self,
        *,
        day_frame: pd.DataFrame,
        expiry: date,
        legs: dict[str, pd.Series],
        entry_ts: pd.Timestamp,
        credit_entry: float,
        spot_entry: float,
    ) -> tuple[pd.Timestamp, pd.DataFrame, str] | None:
        target_credit = (
            credit_entry
            * (1.0 - self.config.profit_target_pct)
        )
        stop_credit = (
            credit_entry
            * self.config.stop_loss_multiple
        )

        active = day_frame[
            (day_frame["expiry"] == expiry)
            & (day_frame["ts"] > entry_ts)
        ]

        for ts, snapshot in active.groupby("ts"):
            exit_legs = self._match_exit_legs(
                exit_snapshot=snapshot,
                legs=legs,
            )

            if exit_legs is None:
                continue

            credit = self._credit(exit_legs)

            if credit <= target_credit:
                return ts, snapshot, "profit_target"

            if credit >= stop_credit:
                return ts, snapshot, "stop_loss"

            if (
                ts.date() == expiry
                and ts.time() >= self.config.exit_time
            ):
                return ts, snapshot, "expiry_exit"

        return None

    @staticmethod
    def _match_exit_legs(
        *,
        exit_snapshot: pd.DataFrame,
        legs: dict[str, pd.Series],
    ) -> dict[str, pd.Series] | None:
        matched: dict[str, pd.Series] = {}

        for name, leg in legs.items():
            option_type = leg["option_type"]
            strike = leg["strike"]

            candidates = exit_snapshot[
                (exit_snapshot["option_type"] == option_type)
                & (exit_snapshot["strike"] == strike)
                & exit_snapshot["ltp"].notna()
            ]

            if candidates.empty:
                return None

            matched[name] = candidates.iloc[0]

        return matched


def trades_to_frame(
    trades: list[BacktestTrade],
) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(
            columns=[
                "entry_ts",
                "exit_ts",
                "expiry",
                "spot_entry",
                "spot_exit",
                "credit_entry",
                "credit_exit",
                "pnl",
                "exit_reason",
            ]
        )

    return pd.DataFrame(
        [trade.__dict__ for trade in trades]
    )