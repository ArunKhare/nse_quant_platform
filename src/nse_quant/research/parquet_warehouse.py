"""Load partitioned historical option-stream Parquet data for research."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd


class ParquetWarehouse:
    """Reads date-partitioned option-stream exports."""

    def __init__(self, warehouse_dir: str | Path) -> None:
        self.warehouse_dir = Path(warehouse_dir)

        if not self.warehouse_dir.exists():
            raise FileNotFoundError(
                f"Parquet warehouse directory does not exist: {self.warehouse_dir}"
            )

    def load_option_stream(
        self,
        *,
        underlying: str,
        start_date: str | date,
        end_date: str | date,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        start = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
        end = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date

        if end < start:
            raise ValueError("end_date must be on or after start_date")

        files = sorted(self.warehouse_dir.glob(f"underlying={underlying}/year=*/month=*/*.parquet"))

        selected: list[Path] = []

        for path in files:
            file_date = self._date_from_filename(path.name)

            if file_date is None:
                continue

            if start <= file_date <= end:
                selected.append(path)

        if not selected:
            return pd.DataFrame()

        frames = [pd.read_parquet(path, columns=columns) for path in selected]

        frame = pd.concat(frames, ignore_index=True)

        if frame.empty:
            return frame

        frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
        frame = frame[(frame["ts"].dt.date >= start) & (frame["ts"].dt.date <= end)]

        return frame.sort_values(["ts", "instrument_token"]).reset_index(drop=True)

    @staticmethod
    def _date_from_filename(filename: str) -> date | None:
        prefix = "option_stream_"
        suffix = ".parquet"

        if not filename.startswith(prefix) or not filename.endswith(suffix):
            return None

        raw = filename[len(prefix) : -len(suffix)]

        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None

    def _build_pattern(
        self,
        *,
        underlying: str,
        start: date,
        end: date,
    ) -> str:
        months: set[tuple[int, int]] = set()

        current = date(start.year, start.month, 1)

        while current <= end:
            months.add((current.year, current.month))

            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(
                    current.year,
                    current.month + 1,
                    1,
                )

        patterns = [
            str(
                self.warehouse_dir
                / f"underlying={underlying}"
                / f"year={year:04d}"
                / f"month={month:02d}"
                / "option_stream_*.parquet"
            )
            for year, month in sorted(months)
        ]

        return "**".join([]) if not patterns else patterns[0]
