from datetime import date, datetime, timedelta

import pytest

from nse_quant.market_data.chain import discover_chain_for_horizon, discover_chain_multi_expiry
from nse_quant.market_data.expiry_selection import (
    ExpirySelectionError,
    select_capture_expiries,
    select_monthly_entry_expiry,
)

AS_OF = date(2025, 1, 1)


def expiry(dte: int) -> date:
    return AS_OF + timedelta(days=dte)


def test_capture_keeps_all_listings_through_first_strictly_beyond_90() -> None:
    dates = [expiry(day) for day in (120, 91, 90, 60, 30, 7, 0, -1, 30)]
    assert select_capture_expiries(dates, as_of=AS_OF) == tuple(expiry(day) for day in (0, 7, 30, 60, 90, 91))


@pytest.mark.parametrize("days", [[], [-1], [7, 30, 90]])
def test_missing_beyond_horizon_fails_closed(days: list[int]) -> None:
    with pytest.raises(ExpirySelectionError, match="beyond_horizon"):
        select_capture_expiries(map(expiry, days), as_of=AS_OF)


@pytest.mark.parametrize("dte", [25, 40])
def test_monthly_entry_boundaries_are_inclusive(dte: int) -> None:
    selected = expiry(dte)
    assert select_monthly_entry_expiry([selected], monthly_expiries=[selected], as_of=AS_OF) == selected


@pytest.mark.parametrize("dte", [24, 41])
def test_monthly_entry_rejects_outside_window(dte: int) -> None:
    with pytest.raises(ExpirySelectionError, match="no_listed_monthly"):
        select_monthly_entry_expiry([expiry(dte)], monthly_expiries=[expiry(dte)], as_of=AS_OF)


def test_weekly_is_never_fallback_and_monthly_must_be_listed() -> None:
    with pytest.raises(ExpirySelectionError):
        select_monthly_entry_expiry([expiry(30)], monthly_expiries=[expiry(35)], as_of=AS_OF)
    with pytest.raises(ExpirySelectionError):
        select_monthly_entry_expiry([expiry(30)], monthly_expiries=[], as_of=AS_OF)


def test_explicit_holiday_adjusted_date_and_earliest_tiebreak() -> None:
    actual = date(2025, 1, 27)
    assert (
        select_monthly_entry_expiry(
            [expiry(35), actual, expiry(30)], monthly_expiries=[expiry(35), actual], as_of=AS_OF
        )
        == actual
    )


def test_invalid_window_and_date_inputs_are_rejected() -> None:
    with pytest.raises(ExpirySelectionError, match="inverted"):
        select_monthly_entry_expiry([], monthly_expiries=[], as_of=AS_OF, min_dte=40, max_dte=25)
    with pytest.raises(ExpirySelectionError, match="calendar_date"):
        select_capture_expiries([datetime(2025, 6, 1)], as_of=AS_OF)
    with pytest.raises(ExpirySelectionError, match="positive_integer"):
        select_capture_expiries([expiry(100)], as_of=AS_OF, horizon_days=0)


def instruments() -> list[dict]:
    rows = []
    for index, day in enumerate((7, 30, 60, 91, 120)):
        for offset, kind in enumerate(("CE", "PE")):
            rows.append(
                dict(
                    name="NIFTY",
                    instrument_type=kind,
                    expiry=expiry(day).isoformat(),
                    strike=25000,
                    tradingsymbol=f"NIFTY-{day}-{kind}",
                    instrument_token=index * 2 + offset + 1,
                    lot_size=75,
                )
            )
    return rows


def test_horizon_chain_discovery_is_replayable_and_expiry_isolated() -> None:
    chains = discover_chain_for_horizon(iter(instruments()), "NIFTY", 25000, as_of=AS_OF)
    assert [day for day, _ in chains] == [expiry(day) for day in (7, 30, 60, 91)]
    for day, contracts in chains:
        assert len(contracts) == 2
        assert all(contract.expiry == day for contract in contracts)
    assert chains == discover_chain_for_horizon(instruments(), "NIFTY", 25000, as_of=AS_OF)


def test_existing_count_api_remains_separate() -> None:
    chains = discover_chain_multi_expiry(instruments(), "NIFTY", 25000, 2, as_of=AS_OF)
    assert [day for day, _ in chains] == [expiry(7), expiry(30)]
