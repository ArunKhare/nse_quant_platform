"""Institutional-regime registration respects enable flags."""

from datetime import timedelta
from typing import Any

import pytest

from nse_quant.core.settings import InstitutionalRegimeSettings
from nse_quant.market_data.replay_provider import (
    ReplayMarketDataProvider,
)
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.evidence_plugins.base import DecisionContext
from nse_quant.research.evidence_plugins.institutional_regime import (
    InstitutionalRegimePlugin,
)


def seed(store: DuckDBStore, context: DecisionContext) -> None:
    for offset, iv in [(-3, 0.125), (-2, 0.175), (-1, 0.25)]:
        store.conn.execute(
            """
            INSERT INTO underlying_iv_observations (
                ts, underlying, expiry, iv, spot, source
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                context.ts + timedelta(minutes=offset),
                context.symbol,
                context.snapshot.expiry,
                iv,
                context.snapshot.spot,
                "atm_average_live",
            ],
        )


def plugin(
    store: DuckDBStore,
    *,
    high_iv_rank_threshold: float = 75.0,
) -> InstitutionalRegimePlugin:
    return InstitutionalRegimePlugin(
        store=store,
        settings=InstitutionalRegimeSettings(
            iv_history_limit=3,
            min_iv_history_observations=3,
            high_iv_rank_threshold=high_iv_rank_threshold,
        ),
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
def test_institutional_regime_registration(
    decision_loop_environment: Any,
    replay_snapshots: Any,
    test_settings: Any,
    global_enabled: bool,
    plugin_enabled: bool,
    expected: bool,
) -> None:
    test_settings.evidence.enabled = global_enabled
    test_settings.evidence.plugins.institutional_regime.enabled = plugin_enabled

    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(provider)

    names = {registered.name for registered in loop.evidence_runner.plugins}

    assert ("institutional_regime" in names) is expected


@pytest.mark.parametrize(
    ("current_iv", "rank", "state"),
    [
        (0.20, 60.0, "NORMAL_IV"),
        (0.21875, 75.0, "HIGH_IV"),
        (0.30, 100.0, "HIGH_IV"),
        (0.10, 0.0, "NORMAL_IV"),
    ],
)
def test_rank_threshold_and_clamping(
    test_store: DuckDBStore,
    decisioncontext_factory,
    current_iv: float,
    rank: float,
    state: str,
) -> None:
    decision_context = decisioncontext_factory(current_iv=current_iv)
    seed(test_store, decision_context)

    result = plugin(test_store).build(decision_context)
    iv = result["components"]["iv_state"]

    assert iv["iv_rank"] == pytest.approx(rank)
    assert iv["state"] == state


def test_threshold_is_inclusive(
    test_store: DuckDBStore,
    decisioncontext_factory,
) -> None:
    decision_context = decisioncontext_factory(current_iv=0.21875)
    seed(test_store, decision_context)

    classifier = InstitutionalRegimePlugin(
        store=test_store,
        settings=InstitutionalRegimeSettings(
            iv_history_limit=3,
            min_iv_history_observations=3,
            high_iv_rank_threshold=75.0,
        ),
    )

    result = classifier.build(decision_context)

    assert result["components"]["iv_state"]["iv_rank"] == 75.0
    assert result["components"]["iv_state"]["state"] == "HIGH_IV"
