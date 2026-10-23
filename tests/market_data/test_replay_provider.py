import pytest

from nse_quant.market_data.replay_provider import (
    ReplayExhaustedError,
    ReplayMarketDataProvider,
)


def test_provider_advances_through_snapshots() -> None:
    snapshots = [object(), object(), object()]
    provider = ReplayMarketDataProvider(snapshots)

    assert provider.get_chain_snapshot() is snapshots[0]
    assert provider.get_chain_snapshot() is snapshots[1]
    assert provider.get_chain_snapshot() is snapshots[2]
    assert provider.remaining == 0


def test_provider_raises_when_exhausted() -> None:
    provider = ReplayMarketDataProvider([object()])

    provider.get_chain_snapshot()

    with pytest.raises(ReplayExhaustedError):
        provider.get_chain_snapshot()
