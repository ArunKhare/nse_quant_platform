from datetime import datetime, timedelta, timezone
from nse_quant.core.constants import MARKET_OPEN_MINUTES, MARKET_CLOSE_MINUTES

def is_market_open_now() -> bool:
    now_ist = datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=5, minutes=30))
    )

    if now_ist.weekday() >= 5:
        return False

    minutes = now_ist.hour * 60 + now_ist.minute
    return MARKET_OPEN_MINUTES <= minutes <= MARKET_CLOSE_MINUTES