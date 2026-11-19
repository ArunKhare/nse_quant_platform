"""Bounded hypothetical spot x additive-volatility research surface, not a smile forecast."""

from __future__ import annotations

import hashlib
import json
import math
import platform
from dataclasses import asdict, dataclass, replace
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nse_quant.data_platform.research_iv_spot_stress import ResearchIvSpotStress
    from nse_quant.data_platform.research_option_model import BsmValues, ScenarioTerms

VERSION = "research-iv-hypothetical-spot-vol-surface@1"
VOL_LOW = 0.000001
VOL_HIGH = 5.0
MAX_VOL_SHIFTS = 8
MAX_CELLS = 128
MAX_SURFACE_BYTES = 262144
VOL_PROFILE = "binary-float-exact-decimal-plus-bps-over-10000-prec128-half-even@1"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def validate_vol_shifts(vol_shifts_bps: tuple[int, ...]) -> tuple[int, ...]:
    if (
        type(vol_shifts_bps) is not tuple
        or not 1 <= len(vol_shifts_bps) <= MAX_VOL_SHIFTS
        or any(type(v) is not int or not -5000 <= v <= 5000 for v in vol_shifts_bps)
        or vol_shifts_bps != tuple(sorted(set(vol_shifts_bps)))
    ):
        raise ValueError("SORTED_UNIQUE_BOUNDED_ADDITIVE_VOL_SHIFTS_REQUIRED")
    return vol_shifts_bps


@dataclass(frozen=True)
class ShiftedVolatility:
    shift_bps: int
    exact_decimal: str
    value: float
    value_hex: str


def shifted_volatility(base_volatility: float, shift_bps: int) -> ShiftedVolatility:
    """1bp means +0.0001 ABSOLUTE annual sigma, not 0.01% relative to base sigma.

    Use exact binary-float Decimal origin, never a rounded decimal approximation of
    solved IV. Bounds are the original kernel's actual float bracket, including its
    binary lower endpoint. Exact and converted coordinates must both stay inside.
    """
    if (
        type(base_volatility) is not float
        or not math.isfinite(base_volatility)
        or not VOL_LOW <= base_volatility <= VOL_HIGH
        or type(shift_bps) is not int
        or not -5000 <= shift_bps <= 5000
    ):
        raise ValueError("BOUNDED_FLOAT_IV_AND_INTEGER_VOL_SHIFT_REQUIRED")
    with localcontext(
        Context(prec=128, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999, clamp=0)
    ):
        exact = Decimal.from_float(base_volatility) + Decimal(shift_bps) / Decimal(10000)
        if not Decimal.from_float(VOL_LOW) <= exact <= Decimal.from_float(VOL_HIGH):
            raise ValueError("HYPOTHETICAL_VOLATILITY_OUTSIDE_KERNEL_BRACKET")
        text = format(exact, "f")
    converted = float(exact)
    if not math.isfinite(converted) or not VOL_LOW <= converted <= VOL_HIGH:
        raise ValueError("CONVERTED_HYPOTHETICAL_VOLATILITY_OUTSIDE_BRACKET")
    return ShiftedVolatility(shift_bps, text, converted, converted.hex())


@dataclass(frozen=True)
class SurfaceVolColumn:
    volatility: ShiftedVolatility
    base_spot_values: BsmValues


@dataclass(frozen=True)
class SpotVolCell:
    spot_shock_bps: int
    vol_shift_bps: int
    shocked_spot_decimal: str
    values: BsmValues
    full_model_price_change: float
    spot_only_change: float
    vol_only_change: float
    interaction_change: float
    reconstruction_roundoff: float


@dataclass(frozen=True)
class ResearchIvSpotVolSurface:
    version: str
    model_version: str
    source_study_fingerprint: str
    source_study_sha256: str
    spot_decimal: str
    terms: ScenarioTerms
    base_volatility: float
    base_volatility_hex: str
    spot_shocks_bps: tuple[int, ...]
    vol_shifts_bps: tuple[int, ...]
    baseline: BsmValues
    columns: tuple[SurfaceVolColumn, ...]
    cells: tuple[SpotVolCell, ...]
    scipy_version: str
    python_version: str
    evidence_fingerprint: str
    volatility_profile: str = VOL_PROFILE
    status: str = "computed_hypothetical_spot_vol_surface"
    hypothetical_volatility_shift_assumed: bool = True
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
    atomic_cross_database_snapshot_asserted: bool = False
    canonical_contract_id: None = None
    event_ts: None = None
    published_at: None = None


def compute_research_iv_spot_vol_surface(
    study: ResearchIvSpotStress,
    *,
    vol_shifts_bps: tuple[int, ...],
) -> ResearchIvSpotVolSurface:
    """Full actual kernel repricing. Study is untrusted input, never native source proof."""
    import scipy

    from nse_quant.data_platform import research_iv_spot_stress as stress
    from nse_quant.data_platform import research_iv_stress_archive_record as record
    from nse_quant.data_platform import research_option_model as model

    if (
        stress.VERSION != "research-iv-fixed-vol-spot-stress@1"
        or stress.MAX_SHOCKS != 16
        or stress.MAX_RESULT_BYTES != 65536
        or record.VERSION != "research-iv-spot-stress-archive-record@1"
        or record.MAX_STUDY_BYTES != stress.MAX_RESULT_BYTES
        or model.VERSION != "research-european-bsm-iv@1"
        or model.SIGMA_LOW != VOL_LOW
        or model.SIGMA_HIGH != VOL_HIGH
    ):
        raise ValueError("UNSUPPORTED_SPOT_VOL_SURFACE_PROFILE")
    validate_vol_shifts(vol_shifts_bps)
    if type(study) is not stress.ResearchIvSpotStress:
        raise ValueError("TYPED_SOURCE_SPOT_STRESS_STUDY_REQUIRED")
    shocks = stress.validate_shocks(study.shocks_bps)
    if (
        type(study.points) is not tuple
        or len(study.points) != len(shocks)
        or any(type(p) is not stress.SpotStressPoint for p in study.points)
        or len(shocks) * len(vol_shifts_bps) > MAX_CELLS
    ):
        raise ValueError("BOUNDED_IMMUTABLE_SURFACE_SOURCE_GRID_REQUIRED")
    raw = stress.canonical(asdict(study))
    if not 0 < len(raw) <= stress.MAX_RESULT_BYTES:
        raise ValueError("SURFACE_SOURCE_STUDY_BYTE_LIMIT")
    record._study(json.loads(raw), list(shocks))
    model.scenario_terms_sha256(study.terms)
    if (
        study.python_version != platform.python_version()
        or study.scipy_version != scipy.__version__
    ):
        raise ValueError("SURFACE_SOURCE_AND_CURRENT_MODEL_RUNTIMES_DIFFER")
    # Validate ALL volatility coordinates before any surface repricing. Never drop a column.
    volatilities = tuple(
        shifted_volatility(study.fixed_implied_volatility, v) for v in vol_shifts_bps
    )
    terms = study.terms

    def evaluate(spot_text: str, sigma: float) -> model.BsmValues:
        with localcontext(
            Context(prec=128, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999, clamp=0)
        ):
            spot, strike = Decimal(spot_text), Decimal(terms.strike)
            if not Decimal("0.05") * strike <= spot <= Decimal("20") * strike:
                raise ValueError("SURFACE_SPOT_STRIKE_RATIO_OUTSIDE_DOMAIN")
        return model.price_and_greeks(
            float(spot),
            model.decimal_input(terms.strike),
            model.decimal_input(terms.assumed_years_to_expiry),
            model.decimal_input(terms.annual_rate),
            model.decimal_input(terms.annual_dividend_yield),
            sigma,
            terms.option_type,
        )

    baseline = evaluate(study.spot_decimal, study.fixed_implied_volatility)
    if asdict(baseline) != asdict(study.baseline):
        raise ValueError("SURFACE_BASELINE_DIFFERS_FROM_SOURCE_STUDY")
    for point, shock in zip(study.points, shocks, strict=True):
        with localcontext(
            Context(prec=128, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999, clamp=0)
        ):
            expected_spot = stress.shocked_spot_decimal(study.spot_decimal, shock)
        original_axis_values = evaluate(expected_spot, study.fixed_implied_volatility)
        if point.shocked_spot_decimal != expected_spot or asdict(original_axis_values) != asdict(
            point.values
        ):
            raise ValueError("SURFACE_SPOT_AXIS_DIFFERS_FROM_SOURCE_STUDY")
    columns = tuple(
        SurfaceVolColumn(v, evaluate(study.spot_decimal, v.value)) for v in volatilities
    )
    cells: list[SpotVolCell] = []
    for point in study.points:
        for column in columns:
            values = evaluate(point.shocked_spot_decimal, column.volatility.value)
            if column.volatility.shift_bps == 0 and asdict(values) != asdict(point.values):
                raise ValueError("SURFACE_ZERO_VOL_COLUMN_DIFFERS_FROM_SOURCE")
            full = values.price - baseline.price
            spot_change = point.model_price_change
            vol_change = column.base_spot_values.price - baseline.price
            interaction = (full - spot_change) - vol_change
            closure = ((spot_change + vol_change) + interaction) - full
            metrics = (full, spot_change, vol_change, interaction, closure)
            if any(not math.isfinite(v) for v in metrics):
                raise ValueError("SURFACE_NONFINITE_INTERACTION_RESULT")
            cells.append(
                SpotVolCell(
                    point.shock_bps,
                    column.volatility.shift_bps,
                    point.shocked_spot_decimal,
                    values,
                    full,
                    spot_change,
                    vol_change,
                    interaction,
                    closure,
                )
            )
    result = ResearchIvSpotVolSurface(
        VERSION,
        model.VERSION,
        study.evidence_fingerprint,
        hashlib.sha256(raw).hexdigest(),
        study.spot_decimal,
        study.terms,
        study.fixed_implied_volatility,
        study.fixed_implied_volatility.hex(),
        shocks,
        vol_shifts_bps,
        baseline,
        columns,
        tuple(cells),
        scipy.__version__,
        platform.python_version(),
        "",
    )
    fingerprint = hashlib.sha256(canonical(asdict(result))).hexdigest()
    result = replace(result, evidence_fingerprint=fingerprint)
    if len(canonical(asdict(result))) > MAX_SURFACE_BYTES:
        raise ValueError("SURFACE_RESULT_BYTE_LIMIT")
    return result
