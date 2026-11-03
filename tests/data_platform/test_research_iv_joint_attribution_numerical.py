"""Actual model/surface/spot-attribution tests supplied for repository QA; not sandbox-run."""

from dataclasses import asdict, replace
from decimal import Decimal

import pytest

from nse_quant.data_platform import research_iv_joint_attribution as joint
from nse_quant.data_platform import research_iv_spot_stress as spot
from nse_quant.data_platform import research_iv_spot_vol_surface as surface_api
from nse_quant.data_platform import research_iv_stress_attribution as old
from nse_quant.data_platform.research_option_model import ScenarioTerms


def source(kind="CE"):
    study = spot.compute_research_iv_spot_stress(
        spot_decimal="100.00",
        terms=ScenarioTerms("100", "0.03", "0.01", "0.75", kind),
        fixed_implied_volatility=0.2,
        shocks_bps=(-100, 0, 100),
    )
    return surface_api.compute_research_iv_spot_vol_surface(study, vol_shifts_bps=(-100, 0, 100))


@pytest.mark.parametrize("kind", ["CE", "PE"], ids=["call", "put"])
def test_actual_surface_joint_terms_and_zero_vol_reduction(kind):
    surface = source(kind)
    before = asdict(surface)
    result = joint.attribute_research_iv_spot_vol_surface(surface)
    assert asdict(surface) == before
    assert len(result.cells) == len(surface.cells) == 9
    assert result.source_surface_fingerprint == surface.evidence_fingerprint
    columns = {c.volatility.shift_bps: c for c in surface.columns}
    for cell, original in zip(result.cells, surface.cells, strict=True):
        assert (cell.spot_shock_bps, cell.vol_shift_bps) == (
            original.spot_shock_bps,
            original.vol_shift_bps,
        )
        expected_spot = old.decompose_spot_move(
            base_spot_decimal=surface.spot_decimal,
            shocked_spot_decimal=original.shocked_spot_decimal,
            baseline_delta=surface.baseline.delta,
            baseline_gamma=surface.baseline.gamma,
            full_model_price_change=original.spot_only_change,
        )
        assert cell.spot == expected_spot
        assert Decimal(cell.nominal_sigma_change_decimal) == Decimal(cell.vol_shift_bps) / 10000
        assert cell.joint.full_joint_model_price_change == original.full_model_price_change
        assert cell.joint.vega_component == surface.baseline.vega_per_vol_unit * (
            cell.joint.effective_sigma_change_float
        )
        assert cell.joint.shifted_sigma_hex == columns[cell.vol_shift_bps].volatility.value_hex
        if cell.vol_shift_bps == 0:
            assert cell.joint.vega_component == 0.0
            assert cell.joint.joint_residual == expected_spot.second_order_residual
    assert result == joint.attribute_research_iv_spot_vol_surface(surface)
    assert not result.current_source_checked and not result.approximation_accuracy_certified
    assert not result.vanna_volga_included and not result.portfolio_pnl_asserted


def test_modified_surface_hash_not_refreshed():
    surface = source()
    with pytest.raises(ValueError, match="SOURCE_FINGERPRINT_MISMATCH"):
        joint.attribute_research_iv_spot_vol_surface(
            replace(surface, evidence_fingerprint="0" * 64)
        )


def test_result_cap_never_returns_prefix(monkeypatch):
    surface = source()
    monkeypatch.setattr(joint, "MAX_ATTRIBUTION_BYTES", 1)
    with pytest.raises(ValueError, match="RESULT_BYTE_LIMIT"):
        joint.attribute_research_iv_spot_vol_surface(surface)
