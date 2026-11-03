"""Real repository model/SciPy numerical tests. No fake model; not sandbox-executed."""

import math
from dataclasses import asdict

import pytest

from nse_quant.data_platform import research_option_model as model
from nse_quant.data_platform.research_iv_spot_stress import compute_research_iv_spot_stress


@pytest.mark.parametrize("kind", ["CE", "PE"], ids=["call", "put"])
def test_actual_kernel_grid_and_zero_shock_reproduce_baseline(kind):
    terms = model.ScenarioTerms("100", "0.05", "0.01", "0.5", kind)
    value = compute_research_iv_spot_stress(
        spot_decimal="100.00",
        terms=terms,
        fixed_implied_volatility=0.2,
        shocks_bps=(-1000, 0, 1000),
    )
    assert value.points[1].values == value.baseline
    assert value.points[1].model_price_change == 0.0
    for point in value.points:
        expected = model.price_and_greeks(
            float(point.shocked_spot_decimal), 100, 0.5, 0.05, 0.01, 0.2, kind
        )
        assert asdict(point.values) == asdict(expected)
        assert point.model_price_change == point.values.price - value.baseline.price
    assert value == compute_research_iv_spot_stress(
        spot_decimal="100.00",
        terms=terms,
        fixed_implied_volatility=0.2,
        shocks_bps=(-1000, 0, 1000),
    )
    changes = [point.model_price_change for point in value.points]
    assert changes == sorted(changes, reverse=kind == "PE")
    assert not value.current_source_checked and not value.portfolio_pnl_asserted
    assert not value.volatility_response_modelled and not value.publication_asserted
    assert not value.decision_eligibility_asserted


def test_real_brentq_iv_can_be_used_without_resolving_each_shock():
    terms = model.ScenarioTerms("100", "0.05", "0", "0.5", "CE")
    premium = format(model.price_and_greeks(100, 100, 0.5, 0.05, 0, 0.2, "CE").price, ".10f")
    solved = model.compute_research_iv(spot_decimal="100", premium_decimal=premium, terms=terms)
    assert solved.status == "computed_research_scenario"
    assert solved.implied_volatility is not None and solved.greeks is not None
    value = compute_research_iv_spot_stress(
        spot_decimal="100",
        terms=terms,
        fixed_implied_volatility=solved.implied_volatility,
        shocks_bps=(-100, 0, 100),
    )
    assert value.baseline == solved.greeks
    assert value.fixed_implied_volatility == solved.implied_volatility


def test_put_call_parity_for_every_actual_stress_cell():
    call_terms = model.ScenarioTerms("100", "0.05", "0.01", "0.5", "CE")
    put_terms = model.ScenarioTerms("100", "0.05", "0.01", "0.5", "PE")
    call = compute_research_iv_spot_stress(
        spot_decimal="100",
        terms=call_terms,
        fixed_implied_volatility=0.2,
        shocks_bps=(-500, 0, 500),
    )
    put = compute_research_iv_spot_stress(
        spot_decimal="100", terms=put_terms, fixed_implied_volatility=0.2, shocks_bps=(-500, 0, 500)
    )
    for c, p in zip(call.points, put.points, strict=True):
        parity = float(c.shocked_spot_decimal) * math.exp(-0.01 * 0.5) - 100 * math.exp(-0.05 * 0.5)
        assert abs((c.values.price - p.values.price) - parity) <= 1e-12


@pytest.mark.parametrize(
    "iv",
    [0.0, 5.000001, float("nan"), float("inf"), True, 1],
    ids=["low", "high", "nan", "infinite", "bool", "int"],
)
def test_invalid_iv_never_clamped(iv):
    with pytest.raises(ValueError):
        compute_research_iv_spot_stress(
            spot_decimal="100",
            terms=model.ScenarioTerms("100", "0", "0", "1", "CE"),
            fixed_implied_volatility=iv,
            shocks_bps=(0,),
        )


def test_ratio_violation_blocks_entire_grid():
    with pytest.raises(ValueError, match="RATIO_OUTSIDE_DOMAIN"):
        compute_research_iv_spot_stress(
            spot_decimal="20",
            terms=model.ScenarioTerms("1", "0", "0", "1", "CE"),
            fixed_implied_volatility=0.2,
            shocks_bps=(0, 1),
        )


def test_exact_input_text_is_not_rounded_out_of_fingerprint():
    terms = model.ScenarioTerms("100", "0", "0", "1", "CE")
    first = compute_research_iv_spot_stress(
        spot_decimal="100", terms=terms, fixed_implied_volatility=0.2, shocks_bps=(0,)
    )
    second = compute_research_iv_spot_stress(
        spot_decimal="100.0", terms=terms, fixed_implied_volatility=0.2, shocks_bps=(0,)
    )
    assert first.baseline == second.baseline
    assert first.evidence_fingerprint != second.evidence_fingerprint


def test_result_bound_never_returns_a_truncated_grid(monkeypatch):
    from nse_quant.data_platform import research_iv_spot_stress as stress

    monkeypatch.setattr(stress, "MAX_RESULT_BYTES", 1)
    with pytest.raises(ValueError, match="RESULT_BYTE_LIMIT"):
        stress.compute_research_iv_spot_stress(
            spot_decimal="100",
            terms=model.ScenarioTerms("100", "0", "0", "1", "CE"),
            fixed_implied_volatility=0.2,
            shocks_bps=(-1, 0, 1),
        )
