"""Tests for the observational institutional IV component."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from nse_quant.core.models import ChainSnapshot, MarketFeatures
from nse_quant.core.settings import InstitutionalRegimeSettings
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.evidence_plugins.base import DecisionContext
from nse_quant.research.evidence_plugins.institutional_regime import (
    InstitutionalRegimePlugin,
)
from nse_quant.research.evidence_plugins.registry import (
    EvidencePluginRunner,
)

TS = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
EXPIRY = date(2026, 11, 5)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[DuckDBStore]:
    database = DuckDBStore(tmp_path / "institutional_regime.duckdb")

    try:
        yield database
    finally:
        database.close()


def context(current_iv: float | None = 0.18) -> DecisionContext:
    return DecisionContext(
        run_id="institutional-test",
        symbol="NIFTY",
        ts=TS,
        snapshot=ChainSnapshot(
            ts=TS,
            underlying="NIFTY",
            spot=24_000.0,
            expiry=EXPIRY,
            quotes=[],
        ),
        features=MarketFeatures(
            ts=TS,
            underlying="NIFTY",
            spot=24_000.0,
            expiry=EXPIRY,
            atm_iv=current_iv,
        ),
        iv_history_count=0,
        current_regime=None,
        effective_regimes=[],
        regime_policy=None,
        spot_instrument_token=256265,
    )


def plugin(
    store: Any,
    *,
    limit: int = 3,
) -> InstitutionalRegimePlugin:
    return InstitutionalRegimePlugin(
        store=store,
        settings=InstitutionalRegimeSettings(
            iv_history_limit=limit,
            min_iv_history_observations=3,
        ),
    )


def insert_iv(
    store: DuckDBStore,
    *,
    offset: int,
    iv: float,
    symbol: str = "NIFTY",
    expiry: date = EXPIRY,
    source: str = "atm_average_live",
) -> None:
    store.conn.execute(
        """
        INSERT INTO underlying_iv_observations (
            ts, underlying, expiry, iv, spot, source
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            TS + timedelta(minutes=offset),
            symbol,
            expiry,
            iv,
            24_000.0,
            source,
        ],
    )


def seed(store: DuckDBStore) -> None:
    for offset, iv in [(-3, 0.125), (-2, 0.175), (-1, 0.25)]:
        insert_iv(store, offset=offset, iv=iv)


def test_iv_state_is_complete_but_full_label_is_not(
    store: DuckDBStore,
) -> None:
    seed(store)

    result = plugin(store).build(context(0.225))
    iv = result["components"]["iv_state"]

    assert result["available"] is True
    assert result["complete"] is False
    assert result["regime_label"] is None
    assert iv["complete"] is True
    assert iv["iv_rank"] == pytest.approx(80.0)
    assert iv["state"] == "HIGH_IV"
    assert result["missing_components"] == [
        "term_structure",
        "skew",
        "price_action",
    ]


def test_future_and_current_history_are_excluded(
    store: DuckDBStore,
) -> None:
    seed(store)
    insert_iv(store, offset=0, iv=0.90)
    insert_iv(store, offset=1, iv=0.95)

    iv = plugin(store).build(context())["components"]["iv_state"]

    assert iv["history_count"] == 3
    assert iv["iv_max"] == 0.25
    assert iv["history_end_ts"] == (TS - timedelta(minutes=1)).isoformat()


def test_symbol_expiry_and_source_are_isolated(
    store: DuckDBStore,
) -> None:
    seed(store)
    insert_iv(
        store,
        offset=-1,
        iv=0.90,
        symbol="BANKNIFTY",
    )
    insert_iv(
        store,
        offset=-1,
        iv=0.90,
        expiry=EXPIRY + timedelta(days=7),
    )
    insert_iv(
        store,
        offset=-4,
        iv=0.90,
        source="other_source",
    )

    iv = plugin(store, limit=10).build(context())["components"]["iv_state"]

    assert iv["history_count"] == 3
    assert iv["iv_max"] == 0.25


def test_latest_observations_are_limited_before_statistics(
    store: DuckDBStore,
) -> None:
    insert_iv(store, offset=-4, iv=0.90)
    seed(store)

    iv = plugin(store).build(context())["components"]["iv_state"]

    assert iv["history_count"] == 3
    assert iv["iv_max"] == 0.25


@pytest.mark.parametrize(
    ("current_iv", "rank", "state"),
    [
        (0.20, 60.0, "NORMAL_IV"),
        (0.2125, 70.0, "HIGH_IV"),
        (0.30, 100.0, "HIGH_IV"),
        (0.10, 0.0, "NORMAL_IV"),
    ],
)
def test_rank_threshold_and_clamping(
    store: DuckDBStore,
    current_iv: float,
    rank: float,
    state: str,
) -> None:
    # Binary-exact endpoints make the threshold boundary reproducible.
    for offset, iv in [
        (-3, 0.125),
        (-2, 0.1875),
        (-1, 0.25),
    ]:
        insert_iv(store, offset=offset, iv=iv)

    result = plugin(store).build(context(current_iv))
    iv = result["components"]["iv_state"]

    assert iv["iv_rank"] == pytest.approx(rank)
    assert iv["state"] == state


def test_insufficient_history_is_explicit(
    store: DuckDBStore,
) -> None:
    insert_iv(store, offset=-1, iv=0.15)

    result = plugin(store).build(context())
    iv = result["components"]["iv_state"]

    assert iv["history_count"] == 1
    assert iv["complete"] is False
    assert iv["iv_rank"] is None
    assert result["reason"] == "insufficient_iv_history"


def test_zero_range_does_not_fabricate_rank(
    store: DuckDBStore,
) -> None:
    for offset in [-3, -2, -1]:
        insert_iv(store, offset=offset, iv=0.15)

    iv = plugin(store).build(context())["components"]["iv_state"]

    assert iv["complete"] is False
    assert iv["iv_rank"] is None
    assert iv["reason"] == "zero_iv_history_range"


@pytest.mark.parametrize(
    "value",
    [None, 0.0, -0.1, float("nan"), float("inf")],
)
def test_invalid_current_iv_is_unavailable(
    store: DuckDBStore,
    value: float | None,
) -> None:
    result = plugin(store).build(context(value))

    assert result["available"] is False
    assert result["reason"] == "invalid_current_iv"
    json.dumps(result, allow_nan=False)


def test_invalid_history_does_not_fill_the_window(
    store: DuckDBStore,
) -> None:
    seed(store)

    for offset, iv in [
        (-4, float("nan")),
        (-5, float("inf")),
        (-6, 0.0),
        (-7, -0.1),
    ]:
        insert_iv(store, offset=offset, iv=iv)

    iv = plugin(store, limit=10).build(context())["components"]["iv_state"]

    assert iv["history_count"] == 3


def test_future_current_inputs_are_unavailable(
    store: DuckDBStore,
) -> None:
    current = context()
    earlier_decision = replace(
        current,
        ts=TS - timedelta(seconds=1),
    )

    result = plugin(store).build(earlier_decision)

    assert result["reason"] == "future_current_input"


def test_missing_inputs_are_unavailable(
    store: DuckDBStore,
) -> None:
    current = replace(context(), snapshot=None)

    assert plugin(store).build(current)["reason"] == "missing_current_inputs"


def test_mismatched_features_are_unavailable(
    store: DuckDBStore,
) -> None:
    current = context()
    features = current.features.model_copy(update={"expiry": EXPIRY + timedelta(days=7)})

    result = plugin(store).build(replace(current, features=features))

    assert result["reason"] == "current_input_mismatch"


def test_runner_contains_database_error() -> None:
    class FailingConnection:
        def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("database unavailable")

    class FailingStore:
        conn = FailingConnection()

    results = EvidencePluginRunner([plugin(FailingStore())]).run(context())

    assert results[0].available is False
    assert results[0].payload["error_type"] == "RuntimeError"


def test_evidence_is_persisted(store: DuckDBStore) -> None:
    seed(store)
    current = context()
    payload = plugin(store).build(current)

    store.write_decision_evidence(
        run_id=current.run_id,
        ts=current.ts,
        symbol=current.symbol,
        plugin="institutional_regime",
        evidence=payload,
    )

    row = store.conn.execute(
        """
        SELECT payload_json
        FROM decision_evidence
        WHERE run_id = ? AND plugin = ?
        """,
        [current.run_id, "institutional_regime"],
    ).fetchone()

    assert row is not None
    saved = json.loads(row[0])
    assert saved["regime_label"] is None
    assert saved["components"]["iv_state"]["history_count"] == 3


def test_disabled_by_default() -> None:
    assert InstitutionalRegimeSettings().enabled is False


def test_history_limit_must_cover_minimum() -> None:
    with pytest.raises(ValidationError):
        InstitutionalRegimeSettings(
            iv_history_limit=2,
            min_iv_history_observations=3,
        )
