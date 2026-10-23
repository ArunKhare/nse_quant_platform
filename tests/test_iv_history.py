from datetime import UTC, date, datetime, timedelta

import pytest

from nse_quant.analytics.features import build_features, iv_rank
from nse_quant.analytics.implied_volatility import implied_volatility
from nse_quant.analytics.iv_history import derive_atm_iv_observations
from nse_quant.core.models import MarketFeatures
from nse_quant.strategy.gates import IvRegimeGate


def test_iv_rank_below_history_minimum_is_zero():
    assert iv_rank(10.0, [15.0, 18.0, 20.0]) == 0.0


def test_iv_rank_above_history_maximum_is_hundred():
    assert iv_rank(25.0, [15.0, 18.0, 20.0]) == 100.0


def test_iv_rank_midpoint_is_fifty():
    assert iv_rank(17.5, [15.0, 20.0]) == 50.0


def test_iv_rank_invalid_current_returns_none():
    assert iv_rank(float("nan"), [15.0, 20.0]) is None
    assert iv_rank(0.0, [15.0, 20.0]) is None
    assert iv_rank(-1.0, [15.0, 20.0]) is None


def test_iv_rank_flat_history_returns_fifty():
    assert iv_rank(18.0, [18.0, 18.0, 18.0]) == 50.0


def test_iv_rank_ignores_invalid_history():
    assert iv_rank(17.5, [0.0, -5.0, float("nan"), 15.0, 20.0]) == 50.0


def test_iv_rank_empty_history_returns_none():
    assert iv_rank(18.0, []) is None


def make_features(iv_rank: float | None) -> MarketFeatures:
    return MarketFeatures(
        ts=datetime.now(UTC),
        underlying="NIFTY",
        spot=25000.0,
        expiry=datetime.now(UTC).date() + timedelta(days=5),
        atm_iv=15.0,
        iv_rank=iv_rank,
        iv_rv_spread=0.10,
    )


def test_cold_start_allows_missing_iv_rank():
    gate = IvRegimeGate()

    result = gate.evaluate(
        make_features(iv_rank=None),
        iv_history_count=0,
    )

    assert result.passed
    assert result.details["mode"] == "COLD_START"


def test_enforced_mode_requires_minimum_history():
    gate = IvRegimeGate()

    result = gate.evaluate(
        make_features(iv_rank=20.0),
        iv_history_count=30,
    )

    assert not result.passed
    assert result.details["mode"] == "ENFORCED"


def test_enforced_mode_passes_sufficient_rank():
    gate = IvRegimeGate()

    result = gate.evaluate(
        make_features(iv_rank=55.0),
        iv_history_count=30,
    )

    assert result.passed
    assert result.details["mode"] == "ENFORCED"


def test_atm_iv_observation_is_derived():
    rows = [
        (
            datetime(2026, 10, 18, 11, 30),
            23000.0,
            date(2026, 10, 19),
            23000.0,
            "CE",
            "NIFTY26O1923000CE",
            1,
            65,
            100.0,
            99.0,
            101.0,
            1000,
            2000,
            0.15,
            None,
            None,
            None,
            None,
        ),
        (
            datetime(2026, 10, 18, 11, 30),
            23000.0,
            date(2026, 10, 19),
            23000.0,
            "PE",
            "NIFTY26O1923000PE",
            2,
            65,
            100.0,
            99.0,
            101.0,
            1000,
            2000,
            0.17,
            None,
            None,
            None,
            None,
        ),
    ]

    observations = derive_atm_iv_observations(
        rows,
        underlying="NIFTY",
    )

    assert len(observations) == 1
    assert observations[0][2] == pytest.approx(0.16)


def test_iv_is_computed_for_atm_call():
    iv = implied_volatility(
        option_price=100.0,
        spot=23000.0,
        strike=23000.0,
        time_to_expiry_years=1 / 365,
        risk_free_rate=0.065,
        option_type="CE",
    )

    assert iv is not None
    assert 0.01 < iv < 5.0


def test_write_option_stream_computes_iv(
    test_store,
    snapshot_factory,
):
    snapshot = snapshot_factory(
        spot=23000.0,
        call_price=120.0,
        put_price=115.0,
    )

    for quote in snapshot.quotes:
        quote.iv = None

    written = test_store.write_option_stream(
        "iv-capture-test",
        snapshot,
    )

    assert written == 2

    rows = test_store.conn.execute(
        """
        SELECT iv
        FROM option_stream
        WHERE run_id = 'iv-capture-test'
        """
    ).fetchall()

    assert len(rows) == 2
    assert all(row[0] is not None for row in rows)

    assert test_store.count_underlying_iv_observations(underlying="NIFTY") == 1


def test_build_features_records_iv_diagnostics(snapshot_factory):
    snapshot = snapshot_factory(
        spot=22550.0,
        call_price=120.0,
        put_price=115.0,
    )
    baseline = build_features(snapshot, now=snapshot.ts)
    current_iv = baseline.atm_iv
    assert current_iv is not None

    history = [current_iv * 0.75, current_iv * 1.25] * 20
    features = build_features(snapshot, iv_history=history, now=snapshot.ts)

    assert features.iv_analytics is not None
    assert features.iv_analytics.current_iv == current_iv
    assert features.iv_analytics.iv_min == pytest.approx(current_iv * 0.75)
    assert features.iv_analytics.iv_max == pytest.approx(current_iv * 1.25)
    assert features.iv_analytics.valid_history_count == 40
    assert features.iv_analytics.iv_rank == 50.0


def test_build_features_iv_rank_at_floor(snapshot_factory):
    snapshot = snapshot_factory(
        spot=22550.0,
        call_price=120.0,
        put_price=115.0,
    )
    baseline = build_features(snapshot, now=snapshot.ts)
    current_iv = baseline.atm_iv
    assert current_iv is not None

    history = [current_iv * 1.5, current_iv * 2.0] * 20
    features = build_features(snapshot, iv_history=history, now=snapshot.ts)

    assert features.iv_rank == 0.0
    assert features.iv_analytics is not None
    assert features.iv_analytics.current_iv == current_iv
    assert features.iv_analytics.iv_min == pytest.approx(current_iv * 1.5)
    assert features.iv_analytics.iv_max == pytest.approx(current_iv * 2.0)
