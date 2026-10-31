"""Execution-quality registration respects both enable flags."""

from typing import Any

import pytest

from nse_quant.market_data.replay_provider import (
    ReplayMarketDataProvider,
)


@pytest.mark.parametrize(
    ("global_enabled", "plugin_enabled", "expected"),
    [
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_execution_quality_registration(
    decision_loop_environment: Any,
    replay_snapshots: Any,
    test_settings: Any,
    global_enabled: bool,
    plugin_enabled: bool,
    expected: bool,
) -> None:
    test_settings.evidence.enabled = global_enabled
    test_settings.evidence.plugins.execution_quality.enabled = plugin_enabled

    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(provider)

    names = {registered.name for registered in loop.evidence_runner.plugins}

    assert ("execution_quality" in names) is expected
