"""Decision-loop registration tests for market context."""

from typing import Any

import pytest

from nse_quant.market_data.replay_provider import (
    ReplayMarketDataProvider,
)


@pytest.mark.parametrize(
    ("evidence_enabled", "plugin_enabled", "expected"),
    [
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_market_context_registration(
    decision_loop_environment: Any,
    replay_snapshots: Any,
    test_settings: Any,
    evidence_enabled: bool,
    plugin_enabled: bool,
    expected: bool,
) -> None:
    test_settings.evidence.enabled = evidence_enabled
    test_settings.evidence.plugins.market_context.enabled = plugin_enabled

    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(provider)

    names = {plugin.name for plugin in loop.evidence_runner.plugins}

    assert ("market_context" in names) is expected
