from datetime import UTC, datetime
from unittest.mock import MagicMock

from nse_quant.features.availability import FeatureAvailability
from nse_quant.features.availability_checker import (
    FeatureAvailabilityChecker,
)


def test_missing_core_history_rejects_before_chain_provider() -> None:
    store = MagicMock()
    store.conn.execute.return_value.fetchone.return_value = [0]

    checker = FeatureAvailabilityChecker(store)

    report = checker.evaluate(
        symbol="NIFTY",
        instrument_token=256265,
        as_of=datetime(2026, 10, 19, tzinfo=UTC),
    )

    assert report.core_status == FeatureAvailability.UNAVAILABLE
    assert report.overall_status == FeatureAvailability.UNAVAILABLE
    assert report.can_evaluate_new_entries is False


def test_partial_htf_history_blocks_entries_but_allows_monitoring() -> None:
    store = MagicMock()

    store.conn.execute.return_value.fetchone.side_effect = [
        [100],  # 1m candles
        [20],   # 15m candles
        [20],   # 60m candles
        [300],  # IV observations
        [300],  # daily spot observations
    ]

    checker = FeatureAvailabilityChecker(store)

    report = checker.evaluate(
        symbol="NIFTY",
        instrument_token=256265,
        as_of=datetime(2026, 10, 19, tzinfo=UTC),
    )

    assert report.core_status == FeatureAvailability.READY
    assert report.htf_status == FeatureAvailability.WARMING_UP
    assert report.overall_status == FeatureAvailability.WARMING_UP
    assert report.can_evaluate_new_entries is False
    assert report.can_monitor_open_positions is True