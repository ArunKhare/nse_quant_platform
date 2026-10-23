from datetime import UTC, datetime, timedelta
from typing import ClassVar

from nse_quant.ops.data_quality import DataQualityChecker


def test_missing_bid_ask_is_warning_not_failure():
    checker = DataQualityChecker(stale_seconds=15)

    class Quote:
        instrument_token = 1
        ltp = 100.0
        bid = None
        ask = None
        volume = 100
        exchange_ts = datetime.now(UTC)
        trade_ts = None
        received_at = datetime.now(UTC)

    class Snapshot:
        quotes: ClassVar[list] = [Quote()]

    report = checker.assess(Snapshot())

    assert report.is_usable
    assert report.missing_bid_ask == 1
    assert any(item.startswith("missing_bid_ask") for item in report.warnings)


def test_stale_quote_is_failure():
    checker = DataQualityChecker(stale_seconds=15)

    class Quote:
        instrument_token = 1
        ltp = 100.0
        bid = 99.0
        ask = 101.0
        volume = 100
        exchange_ts = datetime.now(UTC) - timedelta(seconds=60)
        trade_ts = None
        received_at = datetime.now(UTC)

    class Snapshot:
        quotes: ClassVar[list] = [Quote()]

    report = checker.assess(Snapshot())

    assert not report.is_usable
    assert report.stale
    assert any(item.startswith("stale_quote") for item in report.issues)
