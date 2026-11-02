"""Versioned European BSM research scenarios; no market/identity/eligibility claims."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
from dataclasses import asdict, dataclass, replace
from decimal import Decimal

import scipy
from scipy.optimize import brentq
from scipy.special import ndtr

VERSION = "research-european-bsm-iv@1"
SIGMA_LOW = 0.000001
SIGMA_HIGH = 5.0
PRICE_ATOL = 1e-8
PRICE_RTOL = 1e-10
SOLVER_XTOL = 1e-12
SOLVER_RTOL = 1e-12
MAX_ITERATIONS = 256


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def decimal_input(value: str) -> float:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"-?(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,12})?", value) is None
    ):
        raise ValueError("BOUNDED_PLAIN_DECIMAL_SCENARIO_INPUT_REQUIRED")
    return float(Decimal(value))


@dataclass(frozen=True)
class ScenarioTerms:
    strike: str
    annual_rate: str
    annual_dividend_yield: str
    assumed_years_to_expiry: str
    option_type: str

    def __post_init__(self) -> None:
        strike, rate, dividend, years = (
            decimal_input(value)
            for value in (
                self.strike,
                self.annual_rate,
                self.annual_dividend_yield,
                self.assumed_years_to_expiry,
            )
        )
        if (
            not 1e-8 <= strike <= 1e9
            or not -0.25 <= rate <= 1.0
            or not -0.25 <= dividend <= 1.0
            or not 1e-6 <= years <= 5.0
            or self.option_type not in ("CE", "PE")
        ):
            raise ValueError("RESEARCH_BSM_SCENARIO_DOMAIN_NOT_SUPPORTED")


def scenario_terms_sha256(terms: ScenarioTerms) -> str:
    if type(terms) is not ScenarioTerms:
        raise TypeError("TYPED_RESEARCH_SCENARIO_TERMS_REQUIRED")
    checked = ScenarioTerms(**asdict(terms))
    return _digest([VERSION, asdict(checked)])


@dataclass(frozen=True)
class BsmValues:
    price: float
    delta: float
    gamma: float
    vega_per_vol_unit: float
    theta_per_calendar_day: float
    rho_per_rate_unit: float


def price_and_greeks(
    spot: float,
    strike: float,
    years: float,
    rate: float,
    dividend: float,
    volatility: float,
    option_type: str,
) -> BsmValues:
    """European exercise, continuous dividend/rates; annual fraction, theta /365.

    Vega/rho are per 1.00 absolute volatility/rate, NOT per percentage point.
    This helper does not infer economic time, instrument terms or model suitability.
    """
    if any(
        type(x) not in (int, float) or not math.isfinite(x)
        for x in (spot, strike, years, rate, dividend, volatility)
    ) or (
        not 1e-8 <= spot <= 1e9
        or not 1e-8 <= strike <= 1e9
        or not 0.05 <= spot / strike <= 20.0
        or not 1e-6 <= years <= 5.0
        or not -0.25 <= rate <= 1.0
        or not -0.25 <= dividend <= 1.0
        or not SIGMA_LOW <= volatility <= SIGMA_HIGH
        or option_type not in ("CE", "PE")
    ):
        raise ValueError("FINITE_BOUNDED_RESEARCH_BSM_INPUTS_REQUIRED")
    root_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate - dividend + volatility**2 / 2) * years) / (
        volatility * root_t
    )
    d2 = d1 - volatility * root_t
    discounted_spot = spot * math.exp(-dividend * years)
    discounted_strike = strike * math.exp(-rate * years)
    pdf = math.exp(-0.5 * d1**2) / math.sqrt(2 * math.pi)
    # Price out-of-the-money side first, then parity, reducing ITM cancellation.
    if discounted_spot >= discounted_strike:
        put = discounted_strike * float(ndtr(-d2)) - discounted_spot * float(ndtr(-d1))
        call = put + discounted_spot - discounted_strike
    else:
        call = discounted_spot * float(ndtr(d1)) - discounted_strike * float(ndtr(d2))
        put = call + discounted_strike - discounted_spot
    diffusion = -discounted_spot * pdf * volatility / (2 * root_t)
    if option_type == "CE":
        price = call
        delta = math.exp(-dividend * years) * float(ndtr(d1))
        theta = (
            diffusion
            - rate * discounted_strike * float(ndtr(d2))
            + dividend * discounted_spot * float(ndtr(d1))
        ) / 365.0
        rho = years * discounted_strike * float(ndtr(d2))
    else:
        price = put
        delta = -math.exp(-dividend * years) * float(ndtr(-d1))
        theta = (
            diffusion
            + rate * discounted_strike * float(ndtr(-d2))
            - dividend * discounted_spot * float(ndtr(-d1))
        ) / 365.0
        rho = -years * discounted_strike * float(ndtr(-d2))
    result = BsmValues(
        price,
        delta,
        math.exp(-dividend * years) * pdf / (spot * volatility * root_t),
        discounted_spot * root_t * pdf,
        theta,
        rho,
    )
    if any(not math.isfinite(value) for value in asdict(result).values()) or result.price < 0:
        raise ValueError("RESEARCH_BSM_NUMERICAL_RESULT_NOT_FINITE_OR_NONNEGATIVE")
    return result


@dataclass(frozen=True)
class ResearchIvCandidate:
    calculation_id: str
    model_version: str
    status: str
    reason_codes: tuple[str, ...]
    input_fingerprint: str
    scipy_version: str
    python_version: str
    implied_volatility: float | None = None
    greeks: BsmValues | None = None
    price_residual: float | None = None
    canonical_contract_id: None = None
    model_suitability_verified: bool = False
    underlying_identity_verified: bool = False
    source_acquisition_authenticity_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    publication_asserted: bool = False
    decision_eligibility_asserted: bool = False


def compute_research_iv(
    *,
    spot_decimal: str,
    premium_decimal: str,
    terms: ScenarioTerms,
) -> ResearchIvCandidate:
    scenario_terms_sha256(terms)
    spot, premium = decimal_input(spot_decimal), decimal_input(premium_decimal)
    strike, rate, dividend, years = (
        decimal_input(x)
        for x in (
            terms.strike,
            terms.annual_rate,
            terms.annual_dividend_yield,
            terms.assumed_years_to_expiry,
        )
    )
    if not 1e-8 <= spot <= 1e9 or not 1e-8 <= premium <= 1e9 or not 0.05 <= spot / strike <= 20:
        raise ValueError("RESEARCH_BSM_PRICE_DOMAIN_NOT_SUPPORTED")
    fingerprint = _digest(
        [
            VERSION,
            spot_decimal,
            premium_decimal,
            asdict(terms),
            SIGMA_LOW,
            SIGMA_HIGH,
            PRICE_ATOL,
            PRICE_RTOL,
            SOLVER_XTOL,
            SOLVER_RTOL,
            MAX_ITERATIONS,
            scipy.__version__,
            platform.python_version(),
        ]
    )

    def finish(
        reason: str,
        iv: float | None = None,
        values: BsmValues | None = None,
        residual: float | None = None,
    ) -> ResearchIvCandidate:
        result = ResearchIvCandidate(
            "",
            VERSION,
            "computed_research_scenario" if iv is not None else "review_required",
            (reason,),
            fingerprint,
            scipy.__version__,
            platform.python_version(),
            iv,
            values,
            residual,
        )
        return replace(result, calculation_id=_digest(asdict(result)))

    ds, dk = spot * math.exp(-dividend * years), strike * math.exp(-rate * years)
    lower, upper = (max(ds - dk, 0.0), ds) if terms.option_type == "CE" else (max(dk - ds, 0.0), dk)
    if not lower < premium < upper:
        return finish("PREMIUM_OUTSIDE_STRICT_EUROPEAN_BSM_BOUNDS")
    tolerance = PRICE_ATOL + PRICE_RTOL * max(premium, 1.0)

    def evaluate(sigma: float) -> BsmValues:
        return price_and_greeks(spot, strike, years, rate, dividend, sigma, terms.option_type)

    low, high = evaluate(SIGMA_LOW).price, evaluate(SIGMA_HIGH).price
    if high - low <= tolerance:
        return finish("IV_NOT_NUMERICALLY_IDENTIFIABLE_IN_PROFILE")
    if not low <= premium <= high:
        return finish("IV_OUTSIDE_SUPPORTED_VOLATILITY_BRACKET")
    try:
        root, details = brentq(
            lambda sigma: evaluate(sigma).price - premium,
            SIGMA_LOW,
            SIGMA_HIGH,
            xtol=SOLVER_XTOL,
            rtol=SOLVER_RTOL,
            maxiter=MAX_ITERATIONS,
            full_output=True,
            disp=False,
        )
    except (ValueError, RuntimeError, OverflowError):
        return finish("RESEARCH_IV_SOLVER_DID_NOT_ESTABLISH_ROOT")
    if not details.converged:
        return finish("RESEARCH_IV_SOLVER_DID_NOT_CONVERGE")
    values = evaluate(float(root))
    residual = values.price - premium
    if abs(residual) > tolerance or values.vega_per_vol_unit <= 1e-8:
        return finish("IV_RESIDUAL_OR_LOCAL_IDENTIFIABILITY_NOT_SUPPORTED")
    return finish("EXPLICIT_EUROPEAN_BSM_SCENARIO_SOLVED", float(root), values, residual)
