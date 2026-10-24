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
    contracts: int = 1
    slippage_per_leg: float = 0.50
    brokerage_per_lot: float = 20.0


@dataclass
class BacktestTradeSummary:
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    expiry: date
    spot_entry: float
    spot_exit: float
    credit_entry: float
    credit_exit: float
    pnl: float
    exit_reason: str


@dataclass
class BacktestDiagnostics:
    days: int = 0
    entries: int = 0
    exits: int = 0
    profit_targets: int = 0
    stop_losses: int = 0
    expiry_exits: int = 0
    end_of_day_exits: int = 0
    no_exit: int = 0
    missing_exit_legs: int = 0
    no_valid_entry_snapshot: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "days": self.days,
            "entries": self.entries,
            "exits": self.exits,
            "profit_targets": self.profit_targets,
            "stop_losses": self.stop_losses,
            "expiry_exits": self.expiry_exits,
            "end_of_day_exits": self.end_of_day_exits,
            "no_exit": self.no_exit,
            "missing_exit_legs": self.missing_exit_legs,
        }


Leg = dict[str, float | str]


class IronCondorBacktester:
    """Backtests cash-settled index iron condors from option-stream data."""

    def __init__(
        self,
        frame: pd.DataFrame,
        config: IronCondorConfig | None = None,
    ) -> None:
        if frame.empty:
            raise ValueError("Cannot backtest an empty option-stream frame")

        self.frame = frame.copy()
        self.config = config or IronCondorConfig()
        self.diagnostics = BacktestDiagnostics()

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
            raise ValueError(f"Missing required option-stream columns: {sorted(missing)}")

        self.frame["ts"] = pd.to_datetime(
            self.frame["ts"],
            utc=True,
        )
        self.frame["market_ts"] = self.frame["ts"].dt.tz_convert("Asia/Kolkata")
        self.frame["expiry"] = pd.to_datetime(self.frame["expiry"]).dt.date
        self.frame["trade_date"] = self.frame["market_ts"].dt.date

    def run(self) -> list[BacktestTradeSummary]:
        trades: list[BacktestTradeSummary] = []

        for trade_date, day_frame in self.frame.groupby("trade_date"):
            self.diagnostics.days += 1

            trade = self._backtest_day(
                trade_date=pd.Timestamp(str(trade_date)).date(),
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
    ) -> BacktestTradeSummary | None:
        entry_frame = day_frame[day_frame["market_ts"].dt.time >= self.config.entry_time]

        if entry_frame.empty:
            return None

        entry_timestamps = entry_frame["market_ts"].drop_duplicates().sort_values()

        for entry_ts in entry_timestamps:
            entry_snapshot = entry_frame[entry_frame["market_ts"] == entry_ts]

            expiry = self._select_expiry(entry_snapshot)

            if expiry is None:
                continue

            expiry_snapshot = entry_snapshot[entry_snapshot["expiry"] == expiry]

            legs = self._select_legs(expiry_snapshot)

            if legs is None:
                continue

            credit_entry = self._credit(legs)
            spot_entry = float(expiry_snapshot["spot"].iloc[0])

            self.diagnostics.entries += 1

            exit_result = self._simulate_exit(
                day_frame=day_frame,
                expiry=expiry,
                legs=legs,
                entry_ts=entry_ts,
                credit_entry=credit_entry,
            )

            if exit_result is None:
                self.diagnostics.no_exit += 1
                return None

            (
                exit_ts,
                exit_snapshot,
                exit_reason,
            ) = exit_result

            exit_legs = self._match_exit_legs(
                exit_snapshot=exit_snapshot,
                legs=legs,
            )

            if exit_legs is None:
                self.diagnostics.missing_exit_legs += 1
                return None

            credit_exit = self._credit(exit_legs)
            spot_exit = float(exit_snapshot["spot"].iloc[0])

            pnl = self._net_pnl(
                credit_entry=credit_entry,
                credit_exit=credit_exit,
            )

            self.diagnostics.exits += 1

            if exit_reason == "profit_target":
                self.diagnostics.profit_targets += 1
            elif exit_reason == "stop_loss":
                self.diagnostics.stop_losses += 1
            elif exit_reason == "expiry_exit":
                self.diagnostics.expiry_exits += 1
            elif exit_reason == "end_of_day":
                self.diagnostics.end_of_day_exits += 1

            return BacktestTradeSummary(
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
        self.diagnostics.no_valid_entry_snapshot += 1
        return None

    def _select_expiry(
        self,
        snapshot: pd.DataFrame,
    ) -> date | None:
        expiries = sorted(snapshot["expiry"].unique())

        return expiries[0] if expiries else None

    def _select_legs(
        self,
        snapshot: pd.DataFrame,
    ) -> dict[str, Leg] | None:
        puts = snapshot[
            (snapshot["option_type"] == "PE")
            & snapshot["delta"].notna()
            & (snapshot["delta"] < 0)
            & snapshot["ltp"].notna()
            & (snapshot["ltp"] > 0)
        ].copy()

        calls = snapshot[
            (snapshot["option_type"] == "CE")
            & snapshot["delta"].notna()
            & (snapshot["delta"] > 0)
            & snapshot["ltp"].notna()
            & (snapshot["ltp"] > 0)
        ].copy()

        if puts.empty or calls.empty:
            return None

        puts["abs_delta"] = puts["delta"].abs()
        calls["abs_delta"] = calls["delta"].abs()

        put_candidates = puts.assign(
            delta_distance=(puts["abs_delta"] - self.config.short_delta).abs()
        ).sort_values("delta_distance", kind="stable")
        call_candidates = calls.assign(
            delta_distance=(calls["abs_delta"] - self.config.short_delta).abs()
        ).sort_values("delta_distance", kind="stable")

        def select_short_and_wing(
            candidates: pd.DataFrame,
            available: pd.DataFrame,
            wing_offset: int,
        ) -> tuple[pd.Series, pd.Series] | None:
            for _, short_row in candidates.iterrows():
                long_rows = available[available["strike"] == short_row["strike"] + wing_offset]
                if not long_rows.empty:
                    return short_row, long_rows.iloc[0]
            return None

        put_legs = select_short_and_wing(
            put_candidates,
            puts,
            -self.config.wing_width,
        )
        call_legs = select_short_and_wing(
            call_candidates,
            calls,
            self.config.wing_width,
        )

        if put_legs is None or call_legs is None:
            return None

        short_put_row, long_put_row = put_legs
        short_call_row, long_call_row = call_legs

        return {
            "short_put": self._leg_from_row(short_put_row),
            "long_put": self._leg_from_row(long_put_row),
            "short_call": self._leg_from_row(short_call_row),
            "long_call": self._leg_from_row(long_call_row),
        }

    @staticmethod
    def _leg_from_row(
        row: pd.Series,
    ) -> Leg:
        return {
            "option_type": str(row["option_type"]),
            "strike": float(row["strike"]),
            "ltp": float(row["ltp"]),
            "delta": (float(row["delta"]) if pd.notna(row["delta"]) else float("nan")),
        }

    @staticmethod
    def _credit(
        legs: dict[str, Leg],
    ) -> float:
        return float(
            float(legs["short_put"]["ltp"])
            + float(legs["short_call"]["ltp"])
            - float(legs["long_put"]["ltp"])
            - float(legs["long_call"]["ltp"])
        )

    def _net_pnl(
        self,
        *,
        credit_entry: float,
        credit_exit: float,
    ) -> float:
        entry_credit_after_slippage = credit_entry - 4 * self.config.slippage_per_leg

        exit_credit_after_slippage = credit_exit + 4 * self.config.slippage_per_leg

        gross_pnl = (
            (entry_credit_after_slippage - exit_credit_after_slippage)
            * self.config.lot_size
            * self.config.contracts
        )

        brokerage = self.config.brokerage_per_lot * self.config.lot_size * self.config.contracts

        return float(gross_pnl - brokerage)

    def _simulate_exit(
        self,
        *,
        day_frame: pd.DataFrame,
        expiry: date,
        legs: dict[str, Leg],
        entry_ts: pd.Timestamp,
        credit_entry: float,
    ) -> tuple[pd.Timestamp, pd.DataFrame, str] | None:
        target_credit = credit_entry * (1.0 - self.config.profit_target_pct)
        stop_credit = credit_entry * (self.config.stop_loss_multiple)

        active = day_frame[(day_frame["expiry"] == expiry) & (day_frame["market_ts"] > entry_ts)]

        for ts, snapshot in active.groupby("market_ts"):
            ts = pd.Timestamp(str(ts))

            exit_legs = self._match_exit_legs(
                exit_snapshot=snapshot,
                legs=legs,
            )

            if exit_legs is None:
                continue

            credit = self._credit(exit_legs)

            if credit_entry > 0 and credit <= target_credit:
                return (
                    ts,
                    snapshot,
                    "profit_target",
                )

            if credit_entry > 0 and credit >= stop_credit:
                return ts, snapshot, "stop_loss"

            if ts.date() == expiry and ts.time() >= self.config.exit_time:
                return (
                    ts,
                    snapshot,
                    "expiry_exit",
                )

        final_ts = active["market_ts"].max()

        if pd.isna(final_ts):
            return None

        final_snapshot = active[active["market_ts"] == final_ts]

        final_legs = self._match_exit_legs(
            exit_snapshot=final_snapshot,
            legs=legs,
        )

        if final_legs is None:
            return None

        return (
            pd.Timestamp(final_ts),
            final_snapshot,
            "end_of_day",
        )

    @staticmethod
    def _match_exit_legs(
        *,
        exit_snapshot: pd.DataFrame,
        legs: dict[str, Leg],
    ) -> dict[str, Leg] | None:
        matched: dict[str, Leg] = {}

        for name, leg in legs.items():
            candidates = exit_snapshot[
                (exit_snapshot["option_type"] == leg["option_type"])
                & (exit_snapshot["strike"] == leg["strike"])
                & exit_snapshot["ltp"].notna()
            ]

            if candidates.empty:
                return None

            matched[name] = IronCondorBacktester._leg_from_row(candidates.iloc[0])

        return matched


def trades_to_frame(
    trades: list[BacktestTradeSummary],
) -> pd.DataFrame:
    columns = [
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

    if not trades:
        return pd.DataFrame(columns=columns)

    return pd.DataFrame([trade.__dict__ for trade in trades])
