from datetime import datetime, timedelta

import pytest

from nse_quant.market_data.historical import get_historical_date_range


@pytest.mark.parametrize(
    ("interval", "lookback_days"),
    [
        ("1m", 5),
        ("15m", 30),
        ("60m", 90),
        ("day", 365 * 3),
        ("custom", 30),
    ],
)
def test_get_historical_date_range_uses_interval_lookback(
    interval: str,
    lookback_days: int,
) -> None:
    end_dt = datetime(2026, 10, 18, 12, 0)

    from_dt, to_dt = get_historical_date_range(interval, end_dt)

    assert to_dt == end_dt
    assert from_dt == end_dt - timedelta(days=lookback_days)
