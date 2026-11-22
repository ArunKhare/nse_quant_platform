"""Critical analytical/boundary cases only; no market connections or large histories."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from nse_quant.analytics.constant_maturity_inputs import (
    ForwardPoint,
    PremiumPoint,
    SurfaceInputError,
    black76_forward_delta,
    black76_iv,
    black76_price,
    build_surface_inputs,
    constant_maturity,
    synthetic_forward_from_pair,
)
from nse_quant.market_data.surface_input_adapter import surface_from_batch

NOW = datetime(2026, 1, 2, 10, tzinfo=UTC)


def inputs(
    put_iv: float = 0.2,
) -> tuple[list[PremiumPoint], list[ForwardPoint]]:
    quotes: list[PremiumPoint] = []
    forwards: list[ForwardPoint] = []
    for day in (20, 40, 80, 100):
        expiry = NOW + timedelta(days=day)
        forwards.append(ForwardPoint("NIFTY", expiry, 100.0, 0.05, NOW, NOW, "fixture_futures", f"future-{day}"))
        for strike in (90.0, 95.0, 100.0, 105.0, 110.0):
            for kind in ("CE", "PE"):
                premium = black76_price(100, strike, day / 365, 0.05, 0.2 if kind == "CE" else put_iv, kind)
                quotes.append(
                    PremiumPoint(len(quotes) + 1, "NIFTY", "batch-a", expiry, strike, kind, premium, premium, NOW, NOW)
                )
    return quotes, forwards


def test_black76_analytical_value_parity_and_undiscounted_delta():
    assert black76_price(100, 100, 1, 0, 0.2, "CE") == pytest.approx(7.965567455405804)
    assert black76_forward_delta(100, 100, 1, 0.2, "CE") == pytest.approx(0.539827837277029)
    call = black76_price(105, 100, 1, 0, 0.2, "CE")
    put = black76_price(105, 100, 1, 0, 0.2, "PE")
    assert call - put == pytest.approx(5)


@pytest.mark.parametrize("kind", ["CE", "PE"])
def test_iv_solver_recovers_forward_volatility(kind):
    price = black76_price(100, 103, 30 / 365, 0.07, 0.23, kind)
    assert black76_iv(price, 100, 103, 30 / 365, 0.07, kind) == pytest.approx(0.23)


def test_cm_interpolates_total_variance_not_volatility():
    result = constant_maturity([(NOW + timedelta(days=20), 0.2), (NOW + timedelta(days=40), 0.3)], as_of=NOW, days=30)
    assert result.iv == pytest.approx(((0.5 * 0.2**2 * 20 + 0.5 * 0.3**2 * 40) / 30) ** 0.5)
    assert result.iv != pytest.approx(0.25)
    assert result.upper_weight == 0.5


def test_exact_maturity_and_actual_close_time_are_respected():
    expiry = NOW + timedelta(days=30)
    assert constant_maturity([(expiry, 0.2)], as_of=NOW, days=30).iv == 0.2
    with pytest.raises(SurfaceInputError, match="no_extrapolation"):
        constant_maturity([(expiry + timedelta(minutes=1), 0.2)], as_of=NOW, days=30)


@pytest.mark.parametrize("lower_days", [6, -1])
def test_under_seven_day_expiry_cannot_supply_a_bracket(lower_days):
    with pytest.raises(SurfaceInputError, match="no_extrapolation"):
        constant_maturity(
            [(NOW + timedelta(days=lower_days), 0.2), (NOW + timedelta(days=40), 0.2)], as_of=NOW, days=30
        )


def test_surface_roundtrip_and_call_minus_put_skew():
    quotes, forwards = inputs(put_iv=0.25)
    result = build_surface_inputs(quotes, forwards, as_of=NOW)
    assert result.iv30.iv == pytest.approx(0.2)
    assert result.iv90.iv == pytest.approx(0.2)
    assert result.rr25 == pytest.approx(-0.05)
    assert result.mode == "observation" and result.decision_eligibility_asserted is False
    assert len(result.used_tokens) == 40


@pytest.mark.parametrize("problem", ["mixed_batch", "duplicate_token", "future", "stale", "gap", "crossed"])
def test_bad_surface_batches_fail_closed(problem):
    quotes, forwards = inputs()
    if problem == "mixed_batch":
        quotes[0] = replace(quotes[0], batch_id="other")
    elif problem == "duplicate_token":
        quotes[0] = replace(quotes[0], token=quotes[1].token)
    elif problem == "future":
        quotes[0] = replace(quotes[0], source_time=NOW + timedelta(seconds=1))
    elif problem == "stale":
        quotes[0] = replace(quotes[0], source_time=NOW - timedelta(seconds=301))
    elif problem == "gap":
        quotes[0] = replace(quotes[0], source_time=NOW - timedelta(seconds=31))
    else:
        quotes[0] = replace(quotes[0], ask=quotes[0].bid / 2)
    with pytest.raises(SurfaceInputError):
        build_surface_inputs(quotes, forwards, as_of=NOW)


def test_matching_forward_is_mandatory_no_spot_substitution():
    quotes, forwards = inputs()
    with pytest.raises(SurfaceInputError, match="forward_missing"):
        build_surface_inputs(quotes, forwards[:-1], as_of=NOW)


def test_missing_25_delta_wing_is_not_extrapolated():
    quotes, forwards = inputs()
    quotes = [q for q in quotes if q.option_type != "CE" or q.strike <= 100]
    with pytest.raises(SurfaceInputError, match="no_extrapolation"):
        build_surface_inputs(quotes, forwards, as_of=NOW)


def test_adapter_preserves_batch_and_actual_calendar_provenance_without_mutation():
    quotes, forwards = inputs()
    operational = []
    closes = {}
    for point in quotes:
        expiry = point.expiry_close.date()
        closes[expiry] = point.expiry_close
        operational.append(
            SimpleNamespace(
                instrument_token=point.token,
                bid=point.bid,
                ask=point.ask,
                exchange_ts=point.source_time,
                trade_ts=None,
                received_at=point.received_at,
                instrument=SimpleNamespace(
                    instrument_token=point.token,
                    underlying=point.underlying,
                    expiry=expiry,
                    strike=point.strike,
                    option_type=SimpleNamespace(value=point.option_type),
                ),
            )
        )
    snapshot = SimpleNamespace(run_id="batch-a", underlying="NIFTY", ts=NOW, quotes=operational)
    result = surface_from_batch(
        [snapshot], forwards, expiry_closes=closes, calendar_reference_id="calendar-fixture-v1", as_of=NOW
    )
    assert result.calendar_reference_id == "calendar-fixture-v1" and result.batch_id == "batch-a"
    assert len(snapshot.quotes) == 40
    snapshot.quotes[0].received_at = None
    with pytest.raises(SurfaceInputError, match="genuine_quote"):
        surface_from_batch(
            [snapshot], forwards, expiry_closes=closes, calendar_reference_id="calendar-fixture-v1", as_of=NOW
        )


def test_rr25_interpolates_wing_variances_separately_not_the_rr_value():
    quotes, forwards = inputs()
    revised = []
    for point in quotes:
        days = (point.expiry_close - NOW).days
        sigma = (
            (0.2 if point.option_type == "CE" else 0.25) if days == 20 else (0.3 if point.option_type == "CE" else 0.4)
        )
        premium = black76_price(100, point.strike, days / 365, 0.05, sigma, point.option_type)
        revised.append(replace(point, bid=premium, ask=premium))
    result = build_surface_inputs(revised, forwards, as_of=NOW)
    call30 = ((0.5 * 0.2**2 * 20 + 0.5 * 0.3**2 * 40) / 30) ** 0.5
    put30 = ((0.5 * 0.25**2 * 20 + 0.5 * 0.4**2 * 40) / 30) ** 0.5
    assert result.rr25 == pytest.approx(call30 - put30)
    assert result.rr25 != pytest.approx((-0.05 - 0.1) / 2)


def test_synthetic_forward_uses_the_matched_pair_and_rejects_cross_expiry_pair():
    quotes, _ = inputs()
    call, put = (
        next(q for q in quotes if q.strike == 100 and q.option_type == "CE"),
        next(q for q in quotes if q.strike == 100 and q.option_type == "PE"),
    )
    forward = synthetic_forward_from_pair(call, put, as_of=NOW, rate=0.05)
    assert forward.forward == pytest.approx(100)
    assert len(forward.reference_id) == 64 and forward.source == "synthetic_put_call_parity_mid_v1"
    with pytest.raises(SurfaceInputError, match="matched_call_put"):
        synthetic_forward_from_pair(
            call, replace(put, expiry_close=put.expiry_close + timedelta(days=1)), as_of=NOW, rate=0.05
        )
