"""Pure expiry selection from an as-of instrument/calendar universe.

Capture selection is distinct from strategy entry and interpolation eligibility.
Callers must supply point-in-time listed contracts and authoritative monthly
expiry dates; no weekday or last-visible-expiry inference is performed.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta

EXPIRY_SELECTION_VERSION = "expiry_selection_v1"


class ExpirySelectionError(ValueError):
    pass


def _date(value: date) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ExpirySelectionError("calendar_date_required")
    return value


def _days(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ExpirySelectionError(f"{name}_must_be_positive_integer")
    return value


def select_capture_expiries(
    expiries: Iterable[date], *, as_of: date, horizon_days: int = 90
) -> tuple[date, ...]:
    """Include every unexpired listing through the first strictly beyond horizon.

    Same-day contracts remain capture-eligible; the interpolation builder must
    independently exclude maturities below its seven-day minimum. A listing
    exactly at the horizon does not replace the required beyond-horizon point.
    Missing coverage raises rather than returning a silently truncated set.
    """
    today = _date(as_of)
    horizon = today + timedelta(days=_days(horizon_days, "horizon_days"))
    listed = sorted({_date(expiry) for expiry in expiries if _date(expiry) >= today})
    for index, expiry in enumerate(listed):
        if expiry > horizon:
            return tuple(listed[:index + 1])
    raise ExpirySelectionError("missing_listed_expiry_beyond_horizon")


def select_monthly_entry_expiry(
    listed_expiries: Iterable[date], *, monthly_expiries: Iterable[date],
    as_of: date, min_dte: int = 25, max_dte: int = 40,
) -> date:
    """Select the earliest listed, explicitly designated monthly in [25, 40] DTE.

    Calendar-day DTE uses actual contract dates, including holiday adjustments.
    No weekly fallback is allowed. Multiple eligible monthlies are resolved
    deterministically to the earliest expiry. Calendar authority and version
    must be retained by the calling artifact/provider.
    """
    today = _date(as_of)
    lower = _days(min_dte, "min_dte")
    upper = _days(max_dte, "max_dte")
    if lower > upper:
        raise ExpirySelectionError("inverted_entry_dte_window")
    listed = {_date(expiry) for expiry in listed_expiries}
    monthly = {_date(expiry) for expiry in monthly_expiries}
    eligible = sorted(expiry for expiry in listed & monthly
                      if lower <= (expiry - today).days <= upper)
    if not eligible:
        raise ExpirySelectionError("no_listed_monthly_in_entry_window")
    return eligible[0]
