from datetime import UTC, datetime

from nse_quant.market_data.spot_candle_aggregator import (
    SpotCandleAggregator,
)


def test_aggregates_two_minutes():
    aggregator = SpotCandleAggregator()
    base = datetime(2026, 10, 20, 9, 15, tzinfo=UTC)

    assert (
        aggregator.add_tick(
            ts=base,
            price=23000.0,
            volume=10,
        )
        is None
    )

    assert (
        aggregator.add_tick(
            ts=base.replace(second=30),
            price=23010.0,
            volume=20,
        )
        is None
    )

    candle = aggregator.add_tick(
        ts=base.replace(minute=16),
        price=23020.0,
        volume=5,
    )

    assert candle is not None
    assert candle.open == 23000.0
    assert candle.high == 23010.0
    assert candle.low == 23000.0
    assert candle.close == 23010.0
    assert candle.volume == 30
