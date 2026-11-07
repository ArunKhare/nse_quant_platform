"""Market-session evidence for native strategy inputs.

Classifies a decision timestamp into a market-session state using IST regular
session boundaries. Look-ahead-safe: uses only the supplied decision timestamp.
Observational only; never grants decision eligibility or enables live trading.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from pydantic import BaseModel

from nse_quant.core.constants import IST, REGULAR_SESSION_CLOSE

REGULAR_SESSION_OPEN = time(9, 15)
STATES = ("PRE_MARKET", "REGULAR_SESSION", "POST_MARKET", "CLOSED")


class MarketSessionSettings(BaseModel):
    require_regular_session: bool = False


def classify_market_session(
    *,
    decision_ts: datetime,
    settings: MarketSessionSettings,
) -> dict[str, Any]:
    if decision_ts.tzinfo is None or decision_ts.utcoffset() is None:
        return {
            "available": False,
            "complete": False,
            "state": None,
            "reason": "aware_decision_timestamp_required",
            "decision_eligibility_asserted": False,
        }

    ist_ts = decision_ts.astimezone(IST)
    session_time = ist_ts.time()
    weekday = ist_ts.weekday()

    if weekday >= 5:
        state = "CLOSED"
        reason = "weekend"
    elif session_time < REGULAR_SESSION_OPEN:
        state = "PRE_MARKET"
        reason = None
    elif session_time < REGULAR_SESSION_CLOSE:
        state = "REGULAR_SESSION"
        reason = None
    else:
        state = "POST_MARKET"
        reason = None

    eligible = state == "REGULAR_SESSION" if settings.require_regular_session else None

    return {
        "available": True,
        "complete": True,
        "state": state,
        "decision_ts": decision_ts.isoformat(),
        "ist_time": session_time.isoformat(),
        "weekday": weekday,
        "eligible_for_entry": eligible,
        "reason": reason,
        "decision_eligibility_asserted": False,
    }
