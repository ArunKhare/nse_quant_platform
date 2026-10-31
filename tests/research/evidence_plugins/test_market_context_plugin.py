"""Tests for observational persisted index context."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from nse_quant.core.settings import MarketContextSettings
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.evidence_plugins.base import DecisionContext
from nse_quant.research.evidence_plugins.market_context import (
    MarketContextPlugin,
)
from nse_quant.research.evidence_plugins.registry import (
    EvidencePluginRunner,
)

DECISION_TS = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[DuckDBStore]:
    database = DuckDBStore(tmp_path / "market_context.duckdb")

    try:
        yield database
    finally:
        database.close()


def build_context(
    *,
    ts: datetime = DECISION_TS,
) -> DecisionContext:
    return DecisionContext(
        run_id="context-test",
        symbol="NIFTY",
        ts=ts,
        features=None,
        snapshot=None,
        iv_history_count=0,
        current_regime=None,
        effective_regimes=[],
        regime_policy=None,
        spot_instrument_token=256265,
    )


def build_plugin(
    store: Any,
    *,
    symbols: list[str] | None = None,
    max_age_seconds: int = 300,
) -> MarketContextPlugin:
    return MarketContextPlugin(
        store=store,
        settings=MarketContextSettings(
            symbols=symbols if symbols is not None else ["NIFTY"],
            max_age_seconds=max_age_seconds,
        ),
    )


def write_regime(
    store: DuckDBStore,
    *,
    symbol: str = "NIFTY",
    ts: datetime = DECISION_TS - timedelta(seconds=60),
    regime: str = "RANGE",
) -> None:
    store.write_market_regime(
        symbol=symbol,
        ts=ts,
        trend_regime="RANGE",
        volatility_regime="NORMAL",
        iv_regime="NORMAL_IV",
        regime=regime,
        features={},
    )


def test_no_observations_are_unavailable(
    store: DuckDBStore,
) -> None:
    result = build_plugin(store).build(build_context())
    index = result["context_indices"]["NIFTY"]

    assert result["available"] is False
    assert result["complete"] is False
    assert result["reason"] == "no_context_observations"
    assert index["observation_ts"] is None
    assert index["reason"] == "no_point_in_time_regime"


def test_latest_eligible_observation_is_selected(
    store: DuckDBStore,
) -> None:
    write_regime(
        store,
        ts=DECISION_TS - timedelta(seconds=120),
        regime="TREND_DOWN",
    )
    write_regime(store, regime="RANGE")
    write_regime(
        store,
        ts=DECISION_TS + timedelta(seconds=1),
        regime="TREND_UP",
    )

    result = build_plugin(store).build(build_context())
    index = result["context_indices"]["NIFTY"]

    assert result["available"] is True
    assert result["complete"] is True
    assert result["reason"] is None
    assert index["regime"] == "RANGE"
    assert index["age_seconds"] == 60
    assert index["observation_ts"] == (DECISION_TS - timedelta(seconds=60)).isoformat()


def test_future_only_history_is_unavailable(
    store: DuckDBStore,
) -> None:
    write_regime(
        store,
        ts=DECISION_TS + timedelta(seconds=1),
    )

    result = build_plugin(store).build(build_context())

    assert result["available"] is False
    assert result["context_indices"]["NIFTY"]["regime"] is None


def test_observation_at_decision_time_is_allowed(
    store: DuckDBStore,
) -> None:
    write_regime(store, ts=DECISION_TS)

    result = build_plugin(store).build(build_context())

    assert result["complete"] is True
    assert result["context_indices"]["NIFTY"]["age_seconds"] == 0


@pytest.mark.parametrize(
    ("age_seconds", "complete"),
    [(300, True), (301, False)],
)
def test_freshness_boundary(
    store: DuckDBStore,
    age_seconds: int,
    complete: bool,
) -> None:
    write_regime(
        store,
        ts=DECISION_TS - timedelta(seconds=age_seconds),
    )

    result = build_plugin(store).build(build_context())
    index = result["context_indices"]["NIFTY"]

    assert index["available"] is True
    assert index["complete"] is complete
    assert index["regime"] == "RANGE"
    assert index["reason"] == (None if complete else "stale_regime")


def test_partial_index_coverage_is_incomplete(
    store: DuckDBStore,
) -> None:
    write_regime(store)

    result = build_plugin(
        store,
        symbols=["NIFTY", "BANKNIFTY"],
    ).build(build_context())

    assert result["available"] is True
    assert result["complete"] is False
    assert result["reason"] == "incomplete_context"
    assert result["context_indices"]["NIFTY"]["complete"] is True
    assert result["context_indices"]["BANKNIFTY"]["available"] is False


def test_all_fresh_indices_are_complete(
    store: DuckDBStore,
) -> None:
    write_regime(store)
    write_regime(store, symbol="BANKNIFTY", regime="TREND_UP")

    result = build_plugin(
        store,
        symbols=["NIFTY", "BANKNIFTY"],
    ).build(build_context())

    assert result["available"] is True
    assert result["complete"] is True
    assert result["reason"] is None


@pytest.mark.parametrize("regime", ["UNKNOWN", "", "   "])
def test_unknown_regime_is_incomplete(
    store: DuckDBStore,
    regime: str,
) -> None:
    write_regime(store, regime=regime)

    result = build_plugin(store).build(build_context())
    index = result["context_indices"]["NIFTY"]

    assert index["available"] is True
    assert index["complete"] is False
    assert index["reason"] == "unknown_regime"


def test_null_regime_is_incomplete(store: DuckDBStore) -> None:
    write_regime(store)
    store.conn.execute("UPDATE market_regimes SET regime = NULL")

    result = build_plugin(store).build(build_context())

    assert result["complete"] is False
    assert result["context_indices"]["NIFTY"]["reason"] == "unknown_regime"


def test_unknown_latest_does_not_fall_back(
    store: DuckDBStore,
) -> None:
    write_regime(
        store,
        ts=DECISION_TS - timedelta(seconds=120),
        regime="TREND_UP",
    )
    write_regime(store, regime="UNKNOWN")

    result = build_plugin(store).build(build_context())

    assert result["complete"] is False
    assert result["context_indices"]["NIFTY"]["regime"] == "UNKNOWN"


def test_timezone_offsets_preserve_age(
    store: DuckDBStore,
) -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    write_regime(
        store,
        ts=(DECISION_TS - timedelta(seconds=60)).astimezone(ist),
    )

    result = build_plugin(store).build(build_context(ts=DECISION_TS.astimezone(ist)))

    assert result["as_of"] == DECISION_TS.isoformat()
    assert result["context_indices"]["NIFTY"]["age_seconds"] == 60


def test_naive_decision_timestamp_is_rejected(
    store: DuckDBStore,
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_plugin(store).build(build_context(ts=DECISION_TS.replace(tzinfo=None)))


@pytest.mark.parametrize(
    "symbols",
    [[], [""], [" "], [" NIFTY"], ["NIFTY", "NIFTY"]],
)
def test_invalid_symbols_are_rejected(symbols: list[str]) -> None:
    with pytest.raises(ValidationError):
        MarketContextSettings(symbols=symbols)


@pytest.mark.parametrize("max_age_seconds", [0, -1])
def test_invalid_freshness_is_rejected(
    max_age_seconds: int,
) -> None:
    with pytest.raises(ValidationError):
        MarketContextSettings(max_age_seconds=max_age_seconds)


def test_plugin_is_disabled_by_default() -> None:
    assert MarketContextSettings().enabled is False


def test_runner_contains_plugin_error() -> None:
    class FailingConnection:
        def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("database unavailable")

    class FailingStore:
        conn = FailingConnection()

    results = EvidencePluginRunner([build_plugin(FailingStore())]).run(build_context())

    assert len(results) == 1
    assert results[0].available is False
    assert results[0].complete is False
    assert results[0].payload["error_type"] == "RuntimeError"


def test_payload_is_persisted(store: DuckDBStore) -> None:
    write_regime(store)
    context = build_context()
    result = EvidencePluginRunner([build_plugin(store)]).run(context)[0]

    store.write_decision_evidence(
        run_id=context.run_id,
        ts=context.ts,
        symbol=context.symbol,
        plugin=result.plugin,
        evidence=result.payload,
    )

    rows = store.conn.execute(
        """
        SELECT available, payload_json
        FROM decision_evidence
        WHERE run_id = ?
          AND plugin = ?
        """,
        [context.run_id, "market_context"],
    ).fetchall()

    assert len(rows) == 1
    assert rows[0][0] is True

    payload = json.loads(rows[0][1])
    assert payload["complete"] is True
    assert payload["context_indices"]["NIFTY"]["regime"] == "RANGE"
