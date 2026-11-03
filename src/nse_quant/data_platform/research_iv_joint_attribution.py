"""Baseline delta/gamma plus vega diagnostics of full hypothetical spot/vol repricing."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
from dataclasses import asdict, dataclass, replace
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nse_quant.data_platform.research_iv_spot_vol_surface import ResearchIvSpotVolSurface
    from nse_quant.data_platform.research_iv_stress_attribution import SpotMoveAttribution

VERSION = "research-iv-spot-vol-delta-gamma-vega-attribution@1"
METHOD = "baseline-delta-gamma-plus-vega-effective-float-sigma-change@1"
MAX_ATTRIBUTION_BYTES = 262144
SIGMA_LOW = 0.000001
SIGMA_HIGH = 5.0


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _finite(value: float, *, nonnegative: bool = False) -> float:
    if type(value) not in (int, float):
        raise ValueError("JOINT_ATTRIBUTION_FINITE_NUMBER_REQUIRED")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError("JOINT_ATTRIBUTION_FINITE_NUMBER_REQUIRED") from None
    if not math.isfinite(result) or nonnegative and result < 0:
        raise ValueError("JOINT_ATTRIBUTION_FINITE_NUMBER_REQUIRED")
    return result


@dataclass(frozen=True)
class VegaResidual:
    base_sigma_hex: str
    shifted_sigma_hex: str
    effective_sigma_change_decimal: str
    effective_sigma_change_float: float
    baseline_vega_per_vol_unit: float
    spot_taylor_price_change: float
    full_joint_model_price_change: float
    vega_component: float
    delta_gamma_vega_approximation: float
    joint_residual: float
    reconstruction_roundoff: float


def decompose_vega_residual(
    *,
    base_volatility: float,
    shifted_volatility: float,
    baseline_vega_per_vol_unit: float,
    spot_taylor_price_change: float,
    full_model_price_change: float,
) -> VegaResidual:
    """Vega is per 1.00 ABSOLUTE sigma; use actual model float-coordinate difference.

    This is elementary arithmetic, not a native/model verifier. Residuals/roundoff
    are retained without accuracy thresholds, clipping or correction-to-zero.
    """
    if any(
        type(v) is not float or not math.isfinite(v) or not SIGMA_LOW <= v <= SIGMA_HIGH
        for v in (base_volatility, shifted_volatility)
    ):
        raise ValueError("JOINT_ATTRIBUTION_BOUNDED_FLOAT_SIGMAS_REQUIRED")
    with localcontext(
        Context(prec=128, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999, clamp=0)
    ):
        change = Decimal.from_float(shifted_volatility) - Decimal.from_float(base_volatility)
        text = format(change, "f")
    dsigma = float(change)
    vega = _finite(baseline_vega_per_vol_unit, nonnegative=True)
    spot = _finite(spot_taylor_price_change)
    full = _finite(full_model_price_change)
    vega_term = vega * dsigma
    approximation = spot + vega_term
    residual = full - approximation
    closure = (approximation + residual) - full
    if any(not math.isfinite(v) for v in (dsigma, vega_term, approximation, residual, closure)):
        raise ValueError("JOINT_ATTRIBUTION_NONFINITE_ARITHMETIC")
    return VegaResidual(
        base_volatility.hex(),
        shifted_volatility.hex(),
        text,
        dsigma,
        vega,
        spot,
        full,
        vega_term,
        approximation,
        residual,
        closure,
    )


@dataclass(frozen=True)
class JointAttributionCell:
    spot_shock_bps: int
    vol_shift_bps: int
    nominal_sigma_change_decimal: str
    spot: SpotMoveAttribution
    joint: VegaResidual


@dataclass(frozen=True)
class ResearchIvJointAttribution:
    version: str
    method: str
    source_surface_fingerprint: str
    source_surface_sha256: str
    source_scipy_version: str
    source_python_version: str
    attribution_python_version: str
    cells: tuple[JointAttributionCell, ...]
    evidence_fingerprint: str
    status: str = "computed_research_delta_gamma_vega_attribution"
    current_source_checked: bool = False
    approximation_accuracy_certified: bool = False
    hypothetical_volatility_shift_assumed: bool = True
    vanna_volga_included: bool = False
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


def attribute_research_iv_spot_vol_surface(
    surface: ResearchIvSpotVolSurface,
) -> ResearchIvJointAttribution:
    """Untrusted pure transform. Self-hash/typed structure never establishes source truth."""
    from nse_quant.data_platform import research_iv_spot_stress as spot_api
    from nse_quant.data_platform import research_iv_spot_vol_surface as surface_api
    from nse_quant.data_platform import research_iv_stress_archive_record as record
    from nse_quant.data_platform import research_iv_stress_attribution as spot_attribution
    from nse_quant.data_platform import research_option_model as model

    if (
        surface_api.VERSION != "research-iv-hypothetical-spot-vol-surface@1"
        or surface_api.MAX_SURFACE_BYTES != 262144
        or surface_api.MAX_CELLS != 128
        or surface_api.MAX_VOL_SHIFTS != 8
        or surface_api.VOL_LOW != SIGMA_LOW
        or surface_api.VOL_HIGH != SIGMA_HIGH
        or spot_api.VERSION != "research-iv-fixed-vol-spot-stress@1"
        or spot_api.MAX_SHOCKS != 16
        or spot_attribution.VERSION != "research-iv-spot-stress-delta-gamma-attribution@1"
        or record.VERSION != "research-iv-spot-stress-archive-record@1"
        or model.VERSION != "research-european-bsm-iv@1"
    ):
        raise ValueError("UNSUPPORTED_JOINT_ATTRIBUTION_SURFACE_PROFILE")
    if (
        type(surface) is not surface_api.ResearchIvSpotVolSurface
        or surface.version != surface_api.VERSION
        or surface.model_version != model.VERSION
        or surface.volatility_profile != surface_api.VOL_PROFILE
        or surface.status != "computed_hypothetical_spot_vol_surface"
        or surface.hypothetical_volatility_shift_assumed is not True
        or surface.current_source_checked is not False
        or any(getattr(surface, k) is not False for k in record.DENIALS)
        or any(getattr(surface, k) is not None for k in record.NULLS)
        or not all(
            record.pin(getattr(surface, k))
            for k in (
                "source_study_fingerprint",
                "source_study_sha256",
                "evidence_fingerprint",
            )
        )
    ):
        raise ValueError("TYPED_RESEARCH_ONLY_JOINT_ATTRIBUTION_SOURCE_REQUIRED")
    for label in (surface.scipy_version, surface.python_version):
        if type(label) is not str or re.fullmatch(r"[A-Za-z0-9.+_-]{1,64}", label) is None:
            raise ValueError("JOINT_ATTRIBUTION_SOURCE_RUNTIME_REQUIRED")
    spots = spot_api.validate_shocks(surface.spot_shocks_bps)
    vols = surface_api.validate_vol_shifts(surface.vol_shifts_bps)
    if (
        type(surface.columns) is not tuple
        or len(surface.columns) != len(vols)
        or type(surface.cells) is not tuple
        or len(surface.cells) != len(spots) * len(vols)
        or len(surface.cells) > surface_api.MAX_CELLS
        or type(surface.baseline) is not model.BsmValues
    ):
        raise ValueError("JOINT_ATTRIBUTION_COMPLETE_SURFACE_REQUIRED")
    raw = surface_api.canonical(asdict(surface))
    if not 0 < len(raw) <= surface_api.MAX_SURFACE_BYTES:
        raise ValueError("JOINT_ATTRIBUTION_SOURCE_BYTE_LIMIT")
    unsigned = surface_api.canonical(asdict(replace(surface, evidence_fingerprint="")))
    if hashlib.sha256(unsigned).hexdigest() != surface.evidence_fingerprint:
        raise ValueError("JOINT_ATTRIBUTION_SOURCE_FINGERPRINT_MISMATCH")
    if (
        type(surface.base_volatility) is not float
        or surface.base_volatility_hex != surface.base_volatility.hex()
    ):
        raise ValueError("JOINT_ATTRIBUTION_BASE_SIGMA_BITS_REQUIRED")
    columns: dict[int, surface_api.SurfaceVolColumn] = {}
    for column, shift in zip(surface.columns, vols, strict=True):
        if (
            type(column) is not surface_api.SurfaceVolColumn
            or column.volatility
            != surface_api.shifted_volatility(
                surface.base_volatility,
                shift,
            )
        ):
            raise ValueError("JOINT_ATTRIBUTION_EXACT_VOLATILITY_AXIS_REQUIRED")
        columns[shift] = column
    scopes = [(s, v) for s in spots for v in vols]
    attributed: list[JointAttributionCell] = []
    for cell, scope in zip(surface.cells, scopes, strict=True):
        if (
            type(cell) is not surface_api.SpotVolCell
            or type(cell.spot_shock_bps) is not int
            or type(cell.vol_shift_bps) is not int
            or (cell.spot_shock_bps, cell.vol_shift_bps) != scope
            or type(cell.values) is not model.BsmValues
            or cell.full_model_price_change != cell.values.price - surface.baseline.price
        ):
            raise ValueError("JOINT_ATTRIBUTION_COMPLETE_CELL_SCOPE_REQUIRED")
        with localcontext(
            Context(prec=128, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999, clamp=0)
        ):
            expected_spot = spot_api.shocked_spot_decimal(surface.spot_decimal, cell.spot_shock_bps)
            nominal = format(Decimal(cell.vol_shift_bps) / Decimal(10000), "f")
        if cell.shocked_spot_decimal != expected_spot:
            raise ValueError("JOINT_ATTRIBUTION_EXACT_SPOT_AXIS_REQUIRED")
        spot = spot_attribution.decompose_spot_move(
            base_spot_decimal=surface.spot_decimal,
            shocked_spot_decimal=cell.shocked_spot_decimal,
            baseline_delta=surface.baseline.delta,
            baseline_gamma=surface.baseline.gamma,
            full_model_price_change=cell.spot_only_change,
        )
        joint = decompose_vega_residual(
            base_volatility=surface.base_volatility,
            shifted_volatility=columns[cell.vol_shift_bps].volatility.value,
            baseline_vega_per_vol_unit=surface.baseline.vega_per_vol_unit,
            spot_taylor_price_change=spot.delta_gamma_approximation,
            full_model_price_change=cell.full_model_price_change,
        )
        attributed.append(
            JointAttributionCell(cell.spot_shock_bps, cell.vol_shift_bps, nominal, spot, joint)
        )
    result = ResearchIvJointAttribution(
        VERSION,
        METHOD,
        surface.evidence_fingerprint,
        hashlib.sha256(raw).hexdigest(),
        surface.scipy_version,
        surface.python_version,
        platform.python_version(),
        tuple(attributed),
        "",
    )
    fingerprint = hashlib.sha256(canonical(asdict(result))).hexdigest()
    result = replace(result, evidence_fingerprint=fingerprint)
    if len(canonical(asdict(result))) > MAX_ATTRIBUTION_BYTES:
        raise ValueError("JOINT_ATTRIBUTION_RESULT_BYTE_LIMIT")
    return result
