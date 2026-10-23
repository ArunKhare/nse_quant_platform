"""Immutable domain constants. Deployment tunables belong in config/settings.yaml."""

from __future__ import annotations

from datetime import time
from zoneinfo import ZoneInfo

MARKET_OPEN_MINUTES = 555  # 09:15 IST
MARKET_CLOSE_MINUTES = 930  # 15:30 IST
ENTRY_BLOCK_START_MINUTES = 15
ENTRY_CUTOFF_MINUTES = 885  # 14:45 IST
TRADING_DAYS_PER_YEAR = 252
SECONDS_PER_YEAR = 365.25 * 86400
IV_SOLVER_LOW = 0.0001
IV_SOLVER_HIGH = 5.0
NFO_EXCHANGE = "NFO"
CE = "CE"
PE = "PE"

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 40)
REGULAR_SESSION_OPEN = time(9, 15)
REGULAR_SESSION_CLOSE = time(15, 30)
