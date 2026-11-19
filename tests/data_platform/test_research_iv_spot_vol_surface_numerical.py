"""Actual BSM/stress/codec repricing tests supplied for repository QA, not sandbox-run."""

from dataclasses import asdict

import pytest

from nse_quant.data_platform import research_iv_spot_stress as stress
from nse_quant.data_platform import research_iv_spot_vol_surface as surface
from nse_quant.data_platform import research_option_model as model


def source(kind="CE"):
    return stress.compute_research_iv_spot_stress(
        spot_decimal="100.00",
        terms=model.ScenarioTerms("100", "0.03", "0.01", "0.75", kind),
        fixed_implied_volatility=0.2,
        shocks_bps=(-100, 0, 100),
    )


@pytest.mark.parametrize("kind", ["CE", "PE"], ids=["call", "put"])
def test_actual_kernel_every_cell_and_zero_axes(kind):
    study = source(kind)
    before = asdict(study)
    result = surface.compute_research_iv_spot_vol_surface(study, vol_shifts_bps=(-100, 0, 100))
    assert asdict(study) == before
    assert len(result.cells) == 9 and len(result.columns) == 3
    assert [(p.spot_shock_bps, p.vol_shift_bps) for p in result.cells] == [
        (spot, vol) for spot in (-100, 0, 100) for vol in (-100, 0, 100)
    ]
    columns = {c.volatility.shift_bps: c for c in result.columns}
    original = {p.shock_bps: p for p in study.points}
    for cell in result.cells:
        column = columns[cell.vol_shift_bps]
        expected = model.price_and_greeks(
            float(cell.shocked_spot_decimal), 100, 0.75, 0.03, 0.01, column.volatility.value, kind
        )
        assert asdict(cell.values) == asdict(expected)
        assert cell.full_model_price_change == expected.price - study.baseline.price
        assert (
            cell.interaction_change
            == (cell.full_model_price_change - cell.spot_only_change) - cell.vol_only_change
        )
        if cell.vol_shift_bps == 0:
            assert cell.values == original[cell.spot_shock_bps].values
            assert cell.interaction_change == 0.0
        if cell.spot_shock_bps == 0:
            assert cell.interaction_change == 0.0
    assert result == surface.compute_research_iv_spot_vol_surface(
        study,
        vol_shifts_bps=(-100, 0, 100),
    )
    assert result.hypothetical_volatility_shift_assumed
    assert not result.current_source_checked and not result.volatility_response_modelled
    assert not result.portfolio_pnl_asserted and not result.decision_eligibility_asserted


def test_volatility_columns_are_model_scenarios_not_spot_axis_replacements():
    study = source()
    result = surface.compute_research_iv_spot_vol_surface(study, vol_shifts_bps=(-100, 100))
    assert result.spot_shocks_bps == study.shocks_bps
    assert result.base_volatility.hex() == study.fixed_implied_volatility.hex()
    for shock in study.shocks_bps:
        prices = [cell.values.price for cell in result.cells if cell.spot_shock_bps == shock]
        assert prices == sorted(prices)
    assert any(c.interaction_change != 0.0 for c in result.cells if c.spot_shock_bps != 0)


def test_invalid_derived_volatility_blocks_whole_surface():
    with pytest.raises(ValueError, match="OUTSIDE_KERNEL_BRACKET"):
        surface.compute_research_iv_spot_vol_surface(source(), vol_shifts_bps=(-5000, 0, 100))


def test_surface_result_bound_not_prefix_return(monkeypatch):
    monkeypatch.setattr(surface, "MAX_SURFACE_BYTES", 1)
    with pytest.raises(ValueError, match="SURFACE_RESULT_BYTE_LIMIT"):
        surface.compute_research_iv_spot_vol_surface(source(), vol_shifts_bps=(0,))
