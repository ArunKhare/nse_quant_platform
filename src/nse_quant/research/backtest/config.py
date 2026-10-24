from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field


class BacktestConfig(BaseModel):
    warehouse_dir: Path = Path("data/exports")
    output_dir: Path = Path("data/research/backtests")
    underlying: str = "NIFTY"
    start_date: date
    end_date: date

    market_open: str = "09:15"
    market_close: str = "15:30"
    timezone: str = "Asia/Kolkata"

    initial_capital: float = 1_000_000.0
    slippage_pct: float = 0.0005

    min_snapshots: int = 100
    min_iv_coverage: float = 0.80

    run_id: str = Field(default_factory=lambda: date.today().isoformat())

    max_open_positions: int = 1
    entry_cooldown_minutes: int = 15
