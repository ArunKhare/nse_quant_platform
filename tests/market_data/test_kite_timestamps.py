"""Tests for Kite REST timestamp normalization."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from nse_quant.market_data.kite_timestamps import (
    normalize_kite_rest_timestamp,
)


def test_naive_rest_timestamp_is_interpreted_as_ist() -> None:
    result = normalize_kite_rest_timestamp(
        datetime(2026, 10, 30, 15, 39, 59),
        field="last_trade_time",
    )

    assert result == datetime(2026, 10, 30, 10, 9, 59, tzinfo=UTC)


def test_naive_rest_string_is_interpreted_as_ist() -> None:
    result = normalize_kite_rest_timestamp(
        "2026-10-30 15:39:59",
        field="timestamp",
    )

    assert result == datetime(2026, 10, 30, 10, 9, 59, tzinfo=UTC)


def test_aware_timestamp_preserves_instant() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))

    result = normalize_kite_rest_timestamp(
        datetime(2026, 10, 30, 15, 39, 59, tzinfo=ist),
        field="timestamp",
    )

    assert result == datetime(2026, 10, 30, 10, 9, 59, tzinfo=UTC)


def test_utc_timestamp_is_not_shifted() -> None:
    value = datetime(2026, 10, 30, 10, 9, 59, tzinfo=UTC)

    assert (
        normalize_kite_rest_timestamp(
            value,
            field="timestamp",
        )
        == value
    )


def test_offset_string_preserves_instant() -> None:
    result = normalize_kite_rest_timestamp(
        "2026-10-30T15:39:59+05:30",
        field="timestamp",
    )

    assert result == datetime(2026, 10, 30, 10, 9, 59, tzinfo=UTC)


def test_missing_timestamp_remains_missing() -> None:
    assert (
        normalize_kite_rest_timestamp(
            None,
            field="timestamp",
        )
        is None
    )


@pytest.mark.parametrize(
    "value",
    ["", "not-a-timestamp", 0, 1234567890, {}, []],
)
def test_invalid_timestamp_is_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="Kite REST timestamp"):
        normalize_kite_rest_timestamp(
            value,
            field="timestamp",
        )
