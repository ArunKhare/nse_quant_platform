"""Actual model/stress/codec transform tests supplied for repository QA, not sandbox-run."""

from dataclasses import asdict, replace

import pytest

from nse_quant.data_platform import research_iv_spot_stress as stress
from nse_quant.data_platform import research_iv_stress_attribution as attribution
from nse_quant.data_platform.research_option_model import ScenarioTerms


@pytest.mark.parametrize("kind", ["CE", "PE"], ids=["call", "put"])
def test_actual_bsm_study_decomposes_without_replacing_full_prices(kind):
    study = stress.compute_research_iv_spot_stress(
        spot_decimal="100.00",
        terms=ScenarioTerms("100", "0.05", "0.01", "0.5", kind),
        fixed_implied_volatility=0.2,
        shocks_bps=(-1000, 0, 1000),
    )
    original = asdict(study)
    value = attribution.attribute_research_iv_spot_stress(study)
    assert asdict(study) == original
    assert value.source_study_fingerprint == study.evidence_fingerprint
    assert value.source_python_version == study.python_version
    assert value.source_scipy_version == study.scipy_version
    assert len(value.points) == len(study.points)
    for point, source in zip(value.points, study.points, strict=True):
        part = point.decomposition
        assert point.shock_bps == source.shock_bps
        assert part.full_model_price_change == source.model_price_change
        assert part.delta_component == study.baseline.delta * part.spot_change_float
        assert part.gamma_component == (0.5 * study.baseline.gamma) * (
            part.spot_change_float * part.spot_change_float
        )
        assert part.second_order_residual == (
            part.full_model_price_change - part.delta_gamma_approximation
        )
    zero = value.points[1].decomposition
    assert zero.delta_component == zero.gamma_component == zero.second_order_residual == 0.0
    assert value == attribution.attribute_research_iv_spot_stress(study)
    assert not value.current_source_checked and not value.approximation_accuracy_certified
    assert not value.portfolio_pnl_asserted and not value.decision_eligibility_asserted


def test_malformed_study_fingerprint_not_silently_refreshed():
    study = stress.compute_research_iv_spot_stress(
        spot_decimal="100",
        terms=ScenarioTerms("100", "0", "0", "1", "CE"),
        fixed_implied_volatility=0.2,
        shocks_bps=(0,),
    )
    with pytest.raises(ValueError, match="STUDY_FINGERPRINT_MISMATCH"):
        attribution.attribute_research_iv_spot_stress(replace(study, evidence_fingerprint="0" * 64))


def test_output_limit_never_returns_accepted_prefix(monkeypatch):
    study = stress.compute_research_iv_spot_stress(
        spot_decimal="100",
        terms=ScenarioTerms("100", "0", "0", "1", "CE"),
        fixed_implied_volatility=0.2,
        shocks_bps=(-1, 0, 1),
    )
    monkeypatch.setattr(attribution, "MAX_ATTRIBUTION_BYTES", 1)
    with pytest.raises(ValueError, match="ATTRIBUTION_RESULT_BYTE_LIMIT"):
        attribution.attribute_research_iv_spot_stress(study)
