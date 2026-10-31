"""Tests for persisted institutional term-structure evidence."""

from __future__ import annotations

import json
from collections.abc import Iterator
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

TS = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
NEAR = date(2026, 11, 5)
DEFERRED = date(2026, 11, 12)


@pytest.fixture
def term_store(tmp_path: Path) -> Iterator[DuckDBStore]:
    store = DuckDBStore(tmp_path / "institutional_term.duckdb")
    try:
        yield store
    finally:
        store.close()


def make_context(
    *,
    ts: datetime = TS,
    near_expiry: date = NEAR,
) -> DecisionContext:
    return DecisionContext(
        run_id="term-test",
        symbol="NIFTY",
        ts=ts,
        snapshot=ChainSnapshot(
            ts=ts,
            underlying="NIFTY",
            spot=24_000.0,
            expiry=near_expiry,
            quotes=[],
        ),
        features=MarketFeatures(
            ts=ts,
            underlying="NIFTY",
            spot=24_000.0,
            expiry=near_expiry,
            atm_iv=0.125,
        ),
        iv_history_count=0,
        current_regime=None,
        effective_regimes=[],
        regime_policy=None,
        spot_instrument_token=256265,
    )


def classifier(store: DuckDBStore) -> InstitutionalRegimePlugin:
    return InstitutionalRegimePlugin(
        store=store,
        settings=InstitutionalRegimeSettings(
            iv_history_limit=3,
            min_iv_history_observations=3,
            term_structure_tolerance=0.03125,
            max_term_observation_age_seconds=300,
            max_term_observation_gap_seconds=30,
        ),
    )


def insert(
    store: DuckDBStore,
    *,
    expiry: date,
    iv: float,
    offset_seconds: int = -10,
    symbol: str = "NIFTY",
    source: str = "atm_average_live",
) -> None:
    store.conn.execute(
        """
        INSERT INTO underlying_iv_observations (
            ts, underlying, expiry, iv, spot, source
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            TS + timedelta(seconds=offset_seconds),
            symbol,
            expiry,
            iv,
            24_000.0,
            source,
        ],
    )


def component(store: DuckDBStore) -> dict[str, Any]:
    return classifier(store).build(make_context())["components"]["term_structure"]


@pytest.mark.parametrize(
    ("deferred_iv", "state"),
    [
        (0.1875, "CONTANGO"),
        (0.0625, "BACKWARDATION"),
        (0.125, "FLAT"),
        (0.15625, "FLAT"),
        (0.09375, "FLAT"),
    ],
)
def test_classification_and_exact_boundaries(
    term_store: DuckDBStore,
    deferred_iv: float,
    state: str,
) -> None:
    insert(term_store, expiry=NEAR, iv=0.125)
    insert(term_store, expiry=DEFERRED, iv=deferred_iv)

    result = component(term_store)

    assert result["complete"] is True
    assert result["state"] == state
    assert result["iv_difference"] == deferred_iv - 0.125
    assert result["reason"] is None


def test_missing_deferred_is_explicit(
    term_store: DuckDBStore,
) -> None:
    insert(term_store, expiry=NEAR, iv=0.125)

    result = component(term_store)

    assert result["complete"] is False
    assert result["reason"] == "missing_deferred_observation"


def test_missing_near_is_explicit(
    term_store: DuckDBStore,
) -> None:
    insert(term_store, expiry=DEFERRED, iv=0.1875)

    assert component(term_store)["reason"] == "missing_near_observation"


def test_future_deferred_is_excluded(
    term_store: DuckDBStore,
) -> None:
    insert(term_store, expiry=NEAR, iv=0.125)
    insert(
        term_store,
        expiry=DEFERRED,
        iv=0.1875,
        offset_seconds=1,
    )

    assert component(term_store)["reason"] == "missing_deferred_observation"


@pytest.mark.parametrize(
    ("age", "expected_reason"),
    [(300, None), (301, "stale_term_observation")],
)
def test_age_boundary(
    term_store: DuckDBStore,
    age: int,
    expected_reason: str | None,
) -> None:
    insert(
        term_store,
        expiry=NEAR,
        iv=0.125,
        offset_seconds=-age,
    )
    insert(
        term_store,
        expiry=DEFERRED,
        iv=0.1875,
        offset_seconds=-age,
    )

    assert component(term_store)["reason"] == expected_reason


@pytest.mark.parametrize(
    ("gap", "expected_reason"),
    [(30, None), (31, "term_observation_gap_exceeded")],
)
def test_pair_gap_boundary(
    term_store: DuckDBStore,
    gap: int,
    expected_reason: str | None,
) -> None:
    insert(term_store, expiry=NEAR, iv=0.125)
    insert(
        term_store,
        expiry=DEFERRED,
        iv=0.1875,
        offset_seconds=-10 - gap,
    )

    assert component(term_store)["reason"] == expected_reason


@pytest.mark.parametrize(
    "invalid_iv",
    [0.0, -0.1, float("nan"), float("inf")],
)
def test_invalid_latest_does_not_fall_back(
    term_store: DuckDBStore,
    invalid_iv: float,
) -> None:
    insert(term_store, expiry=NEAR, iv=0.125)
    insert(
        term_store,
        expiry=DEFERRED,
        iv=0.1875,
        offset_seconds=-20,
    )
    insert(
        term_store,
        expiry=DEFERRED,
        iv=invalid_iv,
        offset_seconds=-5,
    )

    result = component(term_store)

    assert result["complete"] is False
    assert result["reason"] == "invalid_deferred_iv"
    assert result["deferred_atm_iv"] is None
    json.dumps(result, allow_nan=False)


def test_symbol_and_source_are_isolated(
    term_store: DuckDBStore,
) -> None:
    insert(term_store, expiry=NEAR, iv=0.125)
    insert(
        term_store,
        expiry=DEFERRED,
        iv=0.1875,
        symbol="BANKNIFTY",
    )
    insert(
        term_store,
        expiry=DEFERRED,
        iv=0.1875,
        source="other_source",
    )

    assert component(term_store)["reason"] == "missing_deferred_observation"


def test_nearest_persisted_deferred_is_not_skipped(
    term_store: DuckDBStore,
) -> None:
    insert(term_store, expiry=NEAR, iv=0.125)
    insert(
        term_store,
        expiry=DEFERRED,
        iv=0.1875,
        offset_seconds=-301,
    )
    insert(
        term_store,
        expiry=DEFERRED + timedelta(days=7),
        iv=0.1875,
    )

    result = component(term_store)

    assert result["deferred_expiry"] == DEFERRED.isoformat()
    assert result["reason"] == "stale_term_observation"


def test_same_timestamp_is_eligible(
    term_store: DuckDBStore,
) -> None:
    insert(
        term_store,
        expiry=NEAR,
        iv=0.125,
        offset_seconds=0,
    )
    insert(
        term_store,
        expiry=DEFERRED,
        iv=0.1875,
        offset_seconds=0,
    )

    result = component(term_store)

    assert result["complete"] is True
    assert result["near_age_seconds"] == 0
    assert result["observation_gap_seconds"] == 0


def test_expiry_close_is_exclusive(
    term_store: DuckDBStore,
) -> None:
    # 10:00 UTC is 15:30 IST.
    current = make_context(near_expiry=TS.date())

    result = classifier(term_store).build(current)
    term = result["components"]["term_structure"]

    assert term["reason"] == "expired_near_expiry"


def test_full_label_remains_unavailable(
    term_store: DuckDBStore,
) -> None:
    insert(term_store, expiry=NEAR, iv=0.125)
    insert(term_store, expiry=DEFERRED, iv=0.1875)

    current = make_context()
    payload = classifier(term_store).build(current)

    assert payload["components"]["term_structure"]["complete"] is True
    assert payload["components"]["skew"]["complete"] is False
    assert payload["components"]["price_action"]["complete"] is False
    assert payload["complete"] is False
    assert payload["regime_label"] is None

    term_store.write_decision_evidence(
        run_id=current.run_id,
        ts=current.ts,
        symbol=current.symbol,
        plugin="institutional_regime",
        evidence=payload,
    )

    row = term_store.conn.execute(
        """
        SELECT payload_json
        FROM decision_evidence
        WHERE run_id = ? AND plugin = ?
        """,
        [current.run_id, "institutional_regime"],
    ).fetchone()

    assert row is not None
    saved = json.loads(row[0])
    assert saved["components"]["term_structure"]["state"] == "CONTANGO"


@pytest.mark.parametrize(
    "updates",
    [
        {"term_structure_tolerance": -0.001},
        {"term_structure_tolerance": float("nan")},
        {"max_term_observation_age_seconds": 0},
        {"max_term_observation_gap_seconds": -1},
    ],
)
def test_invalid_term_settings(
    updates: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        InstitutionalRegimeSettings(**updates)
