from __future__ import annotations

from datetime import date, time
from pathlib import Path
from typing import Any

import pandas as pd

from nse_quant.core.models import (
    ChainSnapshot,
    Instrument,
    OptionQuote,
    OptionType,
)
from nse_quant.research.parquet_warehouse import ParquetWarehouse
from nse_quant.research.warehouse_validation import validate_warehouse

from .config import BacktestConfig

OPTION_TYPE_MAP = {
    "CE": OptionType.CE,
    "PE": OptionType.PE,
}


class HistoricalDataLoader:
    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self.warehouse = ParquetWarehouse(config.warehouse_dir)

    def load_research_grade_days(self) -> list[Path]:
        validation = validate_warehouse(
            self.config.warehouse_dir,
            underlying=self.config.underlying,
            min_snapshots=self.config.min_snapshots,
            min_iv_coverage=self.config.min_iv_coverage,
        )

        valid = validation[validation["status"] == "ok"]

        return [
            Path(path)
            for path in valid["file"]
            if self.config.start_date <= self._date_from_path(path) <= self.config.end_date
        ]

    def load_market_hour_snapshots(self) -> list[ChainSnapshot]:
        frames: list[pd.DataFrame] = []

        for path in self.load_research_grade_days():
            frame = pd.read_parquet(path)
            frames.append(frame)

        if not frames:
            return []

        option_stream = pd.concat(frames, ignore_index=True)
        option_stream["ts"] = pd.to_datetime(option_stream["ts"], utc=True)

        local_time = option_stream["ts"].dt.tz_convert(self.config.timezone).dt.time
        option_stream = option_stream[
            (local_time >= time.fromisoformat(self.config.market_open))
            & (local_time <= time.fromisoformat(self.config.market_close))
        ]

        snapshots: list[ChainSnapshot] = []

        for _, group in option_stream.groupby("ts", sort=True):
            snapshot = self._build_snapshot(group)

            if snapshot is not None:
                snapshots.append(snapshot)

        return snapshots

    def _build_snapshot(self, group: pd.DataFrame) -> ChainSnapshot | None:
        if group.empty:
            return None

        spot = self._resolve_spot(group)

        if spot is None:
            return None

        quotes: list[OptionQuote] = []

        for row in group.itertuples(index=False):
            instrument_token = int(str(row.instrument_token))
            instrument = Instrument(
                tradingsymbol=str(row.tradingsymbol),
                instrument_token=instrument_token,
                underlying=str(row.underlying),
                expiry=pd.Timestamp(str(row.expiry)).date(),
                strike=float(str(row.strike)),
                option_type=OPTION_TYPE_MAP[str(row.option_type).upper()],
                lot_size=int(str(row.lot_size)),
            )

            quotes.append(
                OptionQuote(
                    instrument_token=instrument_token,
                    instrument=instrument,
                    ltp=self._optional_float(row.ltp),
                    bid=self._optional_float(row.bid),
                    ask=self._optional_float(row.ask),
                    volume=self._optional_int(row.volume),
                    oi=self._optional_int(row.oi),
                    iv=self._optional_float(row.iv),
                    received_at=pd.Timestamp(str(row.ts)).to_pydatetime(),
                )
            )

        expiry = quotes[0].instrument.expiry

        return ChainSnapshot(
            ts=group["ts"].iloc[0],
            underlying=self.config.underlying,
            spot=spot,
            expiry=expiry,
            quotes=quotes,
        )

    def _resolve_spot(self, group: pd.DataFrame) -> float | None:
        for column in ("spot", "underlying_spot", "index_spot"):
            if column in group.columns:
                value = group[column].dropna()

                if not value.empty:
                    return float(value.iloc[0])

        return None

    @staticmethod
    def _date_from_path(path: str | Path) -> date:
        name = Path(path).name

        if not name.startswith("option_stream_"):
            raise ValueError(f"Unexpected warehouse file: {name}")

        return pd.Timestamp(name.replace("option_stream_", "").replace(".parquet", "")).date()

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        return None if value is None or pd.isna(value) else float(value)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return None if value is None or pd.isna(value) else int(value)
