"""Integration tests for point-in-time options-positioning evidence."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from nse_quant.core.models import (
    ChainSnapshot,
    Instrument,
    MarketFeatures,
    OptionQuote,
    OptionType,
)
from nse_quant.core.settings import OptionPositioningSettings
from nse_quant.features.feature_store import FeatureStore
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.evidence_plugins.base import DecisionContext
from nse_quant.research.evidence_plugins.option_positioning import (
    OptionPositioningPlugin,
)
from nse_quant.research.evidence_plugins.registry import (
    EvidencePluginRunner,
)

DECISION_TS = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
EXPIRY = date(2026, 11, 5)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[DuckDBStore]:
    database = DuckDBStore(tmp_path / "option_positioning.duckdb")
    try:
        yield database
    finally:
        database.close()


def build_snapshot(
    *,
    ts: datetime = DECISION_TS,
    call_oi: int | None = 100_000,
    put_oi: int | None = 120_000,
    expiry: date = EXPIRY,
) -> ChainSnapshot:
    quotes = []

    for token, option_type, oi in (
        (101, OptionType.CE, call_oi),
        (102, OptionType.PE, put_oi),
    ):
        instrument = Instrument(
            tradingsymbol=f"NIFTY-{expiry}-{option_type.value}",
            instrument_token=token,
            underlying="NIFTY",
            expiry=expiry,
            strike=24_000.0,
            option_type=option_type,
            lot_size=1,
        )
        quotes.append(
            OptionQuote(
                instrument=instrument,
                instrument_token=token,
                ltp=100.0,
                bid=99.0,
                ask=101.0,
                oi=oi,
                iv=0.15,
                received_at=ts,
            )
        )

    return ChainSnapshot(
        ts=ts,
        underlying="NIFTY",
        spot=24_000.0,
        expiry=expiry,
        quotes=quotes,
    )


def build_context(
    snapshot: ChainSnapshot | None,
    *,
    atm_iv: float | None = 0.14,
    expected_move_points: float | None = 180.0,
) -> DecisionContext:
    return DecisionContext(
        run_id="current-run",
        symbol="NIFTY",
        ts=DECISION_TS,
        features=MarketFeatures(
            ts=snapshot.ts if snapshot is not None else DECISION_TS,
            underlying="NIFTY",
            spot=24_000.0,
            expiry=snapshot.expiry if snapshot is not None else EXPIRY,
            atm_iv=atm_iv,
            expected_move_points=expected_move_points,
        ),
        snapshot=snapshot,
        iv_history_count=30,
        current_regime="RANGE",
        effective_regimes=[],
        regime_policy=None,
        spot_instrument_token=256265,
    )


def persist_prior(
    store: DuckDBStore,
    *,
    run_id: str = "prior-run",
    ts: datetime = DECISION_TS - timedelta(minutes=1),
    call_oi: int | None = 100_000,
    put_oi: int | None = 110_000,
    atm_iv: float | None = 0.15,
    expected_move_points: float | None = 190.0,
    expiry: date = EXPIRY,
    save_features: bool = True,
) -> None:
    snapshot = build_snapshot(
        ts=ts,
        call_oi=call_oi,
        put_oi=put_oi,
        expiry=expiry,
    )
    store.write_option_stream(run_id, snapshot)

    if save_features:
        FeatureStore(store.conn).save(
            run_id,
            MarketFeatures(
                ts=ts,
                underlying="NIFTY",
                spot=24_000.0,
                expiry=expiry,
                atm_iv=atm_iv,
                expected_move_points=expected_move_points,
            ),
        )


def build_plugin(store: Any) -> OptionPositioningPlugin:
    return OptionPositioningPlugin(
        store=store,
        settings=OptionPositioningSettings(
            iv_crush_decline_pct=20.0,
        ),
    )


def test_no_prior_snapshot_is_incomplete(store: DuckDBStore) -> None:
    result = build_plugin(store).build(build_context(build_snapshot()))

    assert result["available"] is True
    assert result["complete"] is False
    assert result["pcr"] == pytest.approx(1.2)
    assert result["pcr_change"] is None
    assert result["call_oi_change"] is None
    assert result["put_oi_change"] is None
    assert result["atm_iv_change"] is None
    assert result["expected_move_change"] is None
    assert result["reason"] == "no_prior_snapshot"


def test_prior_snapshot_computes_changes(store: DuckDBStore) -> None:
    persist_prior(store)

    payloads = store.conn.execute("SELECT payload_json FROM option_stream").fetchall()
    assert all(str(row[0]) == "{}" for row in payloads)

    result = build_plugin(store).build(build_context(build_snapshot()))

    assert result["available"] is True
    assert result["complete"] is True
    assert result["pcr"] == pytest.approx(1.2)
    assert result["pcr_change"] == pytest.approx(0.1)
    assert result["call_oi_change"] == 0
    assert result["put_oi_change"] == 10_000
    assert result["atm_iv_change"] == pytest.approx(-0.01)
    assert result["expected_move_change"] == pytest.approx(-10.0)
    assert result["prior_run_id"] == "prior-run"
    assert result["missing_inputs"] == []


def test_iv_crush_is_detected(store: DuckDBStore) -> None:
    persist_prior(store)

    result = build_plugin(store).build(build_context(build_snapshot(), atm_iv=0.10))

    assert result["iv_crush_available"] is True
    assert result["iv_crush_risk"] is True


def test_put_skewed_positioning_is_detected(
    store: DuckDBStore,
) -> None:
    result = build_plugin(store).build(build_context(build_snapshot(put_oi=130_000)))

    assert result["positioning_bias"] == "PUT_SKEWED"


@pytest.mark.parametrize(
    "offset",
    [timedelta(0), timedelta(minutes=1)],
)
def test_current_and_future_snapshots_are_not_prior(
    store: DuckDBStore,
    offset: timedelta,
) -> None:
    persist_prior(store, ts=DECISION_TS + offset)

    result = build_plugin(store).build(build_context(build_snapshot()))

    assert result["complete"] is False
    assert result["prior_snapshot_ts"] is None
    assert result["reason"] == "no_prior_snapshot"


def test_future_history_does_not_replace_prior(
    store: DuckDBStore,
) -> None:
    persist_prior(store)
    persist_prior(
        store,
        run_id="future-run",
        ts=DECISION_TS + timedelta(minutes=1),
        call_oi=1,
        put_oi=1,
        atm_iv=0.80,
    )

    result = build_plugin(store).build(build_context(build_snapshot()))

    assert result["prior_run_id"] == "prior-run"
    assert result["pcr_change"] == pytest.approx(0.1)
    assert result["atm_iv_change"] == pytest.approx(-0.01)


def test_other_expiry_is_excluded(store: DuckDBStore) -> None:
    persist_prior(store)
    persist_prior(
        store,
        run_id="other-expiry",
        ts=DECISION_TS - timedelta(seconds=30),
        expiry=EXPIRY + timedelta(days=7),
        call_oi=1,
        put_oi=1,
    )

    result = build_plugin(store).build(build_context(build_snapshot()))

    assert result["prior_run_id"] == "prior-run"
    assert result["put_oi_change"] == 10_000


def test_runs_at_same_timestamp_are_not_combined(
    store: DuckDBStore,
) -> None:
    persist_prior(store, run_id="a-run")
    persist_prior(
        store,
        run_id="z-run",
        call_oi=50_000,
        put_oi=60_000,
    )

    result = build_plugin(store).build(build_context(build_snapshot()))

    assert result["prior_run_id"] == "z-run"
    assert result["call_oi_change"] == 50_000
    assert result["put_oi_change"] == 60_000
    assert result["complete"] is True


def test_missing_prior_oi_is_not_zero(
    store: DuckDBStore,
) -> None:
    persist_prior(store, call_oi=None)

    result = build_plugin(store).build(build_context(build_snapshot()))

    assert result["complete"] is False
    assert result["call_oi_change"] is None
    assert result["pcr_change"] is None
    assert "prior.call_oi" in result["missing_inputs"]


def test_missing_current_oi_is_not_zero(
    store: DuckDBStore,
) -> None:
    persist_prior(store)

    result = build_plugin(store).build(build_context(build_snapshot(call_oi=None)))

    assert result["call_oi"] is None
    assert result["call_oi_change"] is None
    assert result["pcr"] is None
    assert result["complete"] is False


def test_zero_oi_remains_a_valid_total(
    store: DuckDBStore,
) -> None:
    persist_prior(store, put_oi=0)

    result = build_plugin(store).build(build_context(build_snapshot()))

    assert result["complete"] is True
    assert result["put_oi_change"] == 120_000
    assert result["pcr_change"] == pytest.approx(1.2)


def test_missing_prior_features_preserves_oi_changes(
    store: DuckDBStore,
) -> None:
    persist_prior(store, save_features=False)

    result = build_plugin(store).build(build_context(build_snapshot(), atm_iv=0.10))

    assert result["complete"] is False
    assert result["pcr_change"] == pytest.approx(0.1)
    assert result["put_oi_change"] == 10_000
    assert result["atm_iv_change"] is None
    assert result["expected_move_change"] is None
    assert result["iv_crush_available"] is False
    assert result["iv_crush_risk"] is False
    assert "prior.atm_iv" in result["missing_inputs"]
    assert "prior.expected_move" in result["missing_inputs"]


def test_features_from_another_run_are_not_used(
    store: DuckDBStore,
) -> None:
    persist_prior(store, run_id="a-run")
    persist_prior(
        store,
        run_id="z-run",
        save_features=False,
    )

    result = build_plugin(store).build(build_context(build_snapshot()))

    assert result["prior_run_id"] == "z-run"
    assert result["atm_iv_change"] is None
    assert result["expected_move_change"] is None
    assert result["complete"] is False


def test_missing_snapshot_is_unavailable(
    store: DuckDBStore,
) -> None:
    result = build_plugin(store).build(build_context(None))

    assert result["available"] is False
    assert result["complete"] is False
    assert result["reason"] == "missing_snapshot"


def test_future_current_snapshot_is_unavailable(
    store: DuckDBStore,
) -> None:
    snapshot = build_snapshot(ts=DECISION_TS + timedelta(minutes=1))

    result = build_plugin(store).build(build_context(snapshot))

    assert result["available"] is False
    assert result["reason"] == "future_current_input"


def test_plugin_error_is_contained_by_runner() -> None:
    class FailingConnection:
        def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("database unavailable")

    class FailingStore:
        conn = FailingConnection()

    results = EvidencePluginRunner([build_plugin(FailingStore())]).run(
        build_context(build_snapshot())
    )

    assert len(results) == 1
    assert results[0].plugin == "option_positioning"
    assert results[0].available is False
    assert results[0].complete is False
    assert results[0].payload["error_type"] == "RuntimeError"
