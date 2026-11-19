"""Bounded fixed-IV hypothetical spot-shock study; never portfolio P&L or admission."""

from __future__ import annotations

import hashlib
import json
import platform
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nse_quant.data_platform.research_option_model import BsmValues, ScenarioTerms

VERSION = "research-iv-fixed-vol-spot-stress@1"
MAX_SHOCKS = 16
MAX_RESULT_BYTES = 65536


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def validate_shocks(shocks_bps: tuple[int, ...]) -> tuple[int, ...]:
    if (
        type(shocks_bps) is not tuple
        or not 1 <= len(shocks_bps) <= MAX_SHOCKS
        or any(type(x) is not int or not -5000 <= x <= 5000 for x in shocks_bps)
        or shocks_bps != tuple(sorted(set(shocks_bps)))
    ):
        raise ValueError("SORTED_UNIQUE_BOUNDED_RESEARCH_SPOT_SHOCKS_REQUIRED")
    return shocks_bps


def shocked_spot_decimal(spot_decimal: str, shock_bps: int) -> str:
    """Exact derived decimal, <=16 fractional places; no rounding or clamping.

    Original input retains kernel's <=12 fractional places. A basis-point shock
    adds at most four fractional places. Decimal context is explicit, not ambient.
    """
    if (
        type(spot_decimal) is not str
        or re.fullmatch(r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,12})?", spot_decimal) is None
        or type(shock_bps) is not int
        or not -5000 <= shock_bps <= 5000
    ):
        raise ValueError("BOUNDED_EXACT_RESEARCH_SPOT_AND_SHOCK_REQUIRED")
    with localcontext() as context:
        context.prec = 64
        spot = Decimal(spot_decimal)
        if not Decimal("0.00000001") <= spot <= Decimal("1000000000"):
            raise ValueError("RESEARCH_STRESS_ORIGINAL_SPOT_OUTSIDE_DOMAIN")
        derived = spot * Decimal(10000 + shock_bps) / Decimal(10000)
        if not Decimal("0.00000001") <= derived <= Decimal("1000000000"):
            raise ValueError("RESEARCH_STRESS_DERIVED_SPOT_OUTSIDE_DOMAIN")
        return format(derived, "f")


@dataclass(frozen=True)
class SpotStressPoint:
    shock_bps: int
    shocked_spot_decimal: str
    values: BsmValues
    model_price_change: float


@dataclass(frozen=True)
class ResearchIvSpotStress:
    version: str
    model_version: str
    spot_decimal: str
    terms: ScenarioTerms
    fixed_implied_volatility: float
    shocks_bps: tuple[int, ...]
    baseline: BsmValues
    points: tuple[SpotStressPoint, ...]
    scipy_version: str
    python_version: str
    evidence_fingerprint: str
    status: str = "computed_fixed_iv_hypothetical_spot_stress"
    current_source_checked: bool = False
    portfolio_pnl_asserted: bool = False
    volatility_response_modelled: bool = False
    option_underlying_identity_binding_verified: bool = False
    scenario_terms_authoritative: bool = False
    model_suitability_verified: bool = False
    source_acquisition_authenticity_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    publication_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_contract_id: None = None
    event_ts: None = None
    published_at: None = None


def compute_research_iv_spot_stress(
    *,
    spot_decimal: str,
    terms: ScenarioTerms,
    fixed_implied_volatility: float,
    shocks_bps: tuple[int, ...],
) -> ResearchIvSpotStress:
    """Pure numerical calculation, no source/audit claim. Every cell uses actual @1 kernel."""
    import scipy

    from nse_quant.data_platform import research_option_model as model

    validate_shocks(shocks_bps)
    if (
        model.VERSION != "research-european-bsm-iv@1"
        or model.SIGMA_LOW != 0.000001
        or model.SIGMA_HIGH != 5.0
    ):
        raise ValueError("RESEARCH_STRESS_UNSUPPORTED_MODEL_PROFILE")
    model.scenario_terms_sha256(terms)
    if type(fixed_implied_volatility) is not float:
        raise ValueError("RESEARCH_STRESS_EXACT_FLOAT_IV_REQUIRED")
    baseline_spot = shocked_spot_decimal(spot_decimal, 0)
    strike = Decimal(terms.strike)

    def evaluate(spot_text: str) -> model.BsmValues:
        with localcontext() as context:
            context.prec = 64
            if not Decimal("0.05") * strike <= Decimal(spot_text) <= Decimal("20") * strike:
                raise ValueError("RESEARCH_STRESS_SPOT_STRIKE_RATIO_OUTSIDE_DOMAIN")
        return model.price_and_greeks(
            float(Decimal(spot_text)),
            model.decimal_input(terms.strike),
            model.decimal_input(terms.assumed_years_to_expiry),
            model.decimal_input(terms.annual_rate),
            model.decimal_input(terms.annual_dividend_yield),
            fixed_implied_volatility,
            terms.option_type,
        )

    baseline = evaluate(baseline_spot)
    points: list[SpotStressPoint] = []
    for shock in shocks_bps:
        text = shocked_spot_decimal(spot_decimal, shock)
        values = evaluate(text)
        points.append(SpotStressPoint(shock, text, values, values.price - baseline.price))
    content = [
        VERSION,
        model.VERSION,
        spot_decimal,
        asdict(terms),
        fixed_implied_volatility,
        shocks_bps,
        asdict(baseline),
        [asdict(p) for p in points],
        scipy.__version__,
        platform.python_version(),
    ]
    fingerprint = hashlib.sha256(canonical(content)).hexdigest()
    result = ResearchIvSpotStress(
        VERSION,
        model.VERSION,
        spot_decimal,
        terms,
        fixed_implied_volatility,
        shocks_bps,
        baseline,
        tuple(points),
        scipy.__version__,
        platform.python_version(),
        fingerprint,
    )
    if len(canonical(asdict(result))) > MAX_RESULT_BYTES:
        raise ValueError("RESEARCH_STRESS_RESULT_BYTE_LIMIT")
    return result
