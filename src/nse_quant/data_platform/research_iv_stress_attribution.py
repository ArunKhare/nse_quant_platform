"""Baseline delta/gamma Taylor diagnostics; not P&L, accuracy certification or native proof."""

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
    from nse_quant.data_platform.research_iv_spot_stress import ResearchIvSpotStress

VERSION = "research-iv-spot-stress-delta-gamma-attribution@1"
METHOD = "baseline-delta-ds-plus-half-gamma-ds-squared@1"
MAX_ATTRIBUTION_BYTES = 65536
DECIMAL_PROFILE = "precision64-half-even-emin-999999-emax999999-clamp0@1"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _number(value: float, *, nonnegative: bool = False) -> float:
    if type(value) not in (int, float):
        raise ValueError("ATTRIBUTION_FINITE_NUMERIC_INPUT_REQUIRED")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError("ATTRIBUTION_FINITE_NUMERIC_INPUT_REQUIRED") from None
    if not math.isfinite(result) or nonnegative and result < 0:
        raise ValueError("ATTRIBUTION_FINITE_NUMERIC_INPUT_REQUIRED")
    return result


@dataclass(frozen=True)
class SpotMoveAttribution:
    base_spot_decimal: str
    shocked_spot_decimal: str
    spot_change_decimal: str
    spot_change_float: float
    baseline_delta: float
    baseline_gamma: float
    full_model_price_change: float
    delta_component: float
    gamma_component: float
    delta_gamma_approximation: float
    delta_only_residual: float
    second_order_residual: float
    reconstruction_roundoff: float


def decompose_spot_move(
    *,
    base_spot_decimal: str,
    shocked_spot_decimal: str,
    baseline_delta: float,
    baseline_gamma: float,
    full_model_price_change: float,
) -> SpotMoveAttribution:
    """Actual arithmetic, no model substitute. Exact Decimal subtraction before float conversion.

    Fixed evaluation order is part of @1. Residual/roundoff are exposed, not forced
    to zero, used as acceptance tolerances or claimed to be rigorous error bounds.
    """
    for text, digits in ((base_spot_decimal, 12), (shocked_spot_decimal, 16)):
        if (
            type(text) is not str
            or re.fullmatch(
                r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1," + str(digits) + r"})?",
                text,
            )
            is None
        ):
            raise ValueError("ATTRIBUTION_BOUNDED_EXACT_SPOT_STRINGS_REQUIRED")
    with localcontext(
        Context(prec=64, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999, clamp=0)
    ):
        base, shocked = Decimal(base_spot_decimal), Decimal(shocked_spot_decimal)
        if (
            not Decimal("0.00000001") <= base <= Decimal("1000000000")
            or not Decimal("0.00000001") <= shocked <= Decimal("1000000000")
            or not base * Decimal("0.5") <= shocked <= base * Decimal("1.5")
        ):
            raise ValueError("ATTRIBUTION_SPOT_PROFILE_REQUIRED")
        change = format(shocked - base, "f")
    ds = float(Decimal(change))
    delta = _number(baseline_delta)
    gamma = _number(baseline_gamma, nonnegative=True)
    full = _number(full_model_price_change)
    linear = delta * ds
    quadratic = (0.5 * gamma) * (ds * ds)
    approximation = linear + quadratic
    linear_residual = full - linear
    residual = full - approximation
    closure = (approximation + residual) - full
    if any(
        not math.isfinite(x)
        for x in (
            ds,
            linear,
            quadratic,
            approximation,
            linear_residual,
            residual,
            closure,
        )
    ):
        raise ValueError("ATTRIBUTION_ARITHMETIC_NONFINITE")
    return SpotMoveAttribution(
        base_spot_decimal,
        shocked_spot_decimal,
        change,
        ds,
        delta,
        gamma,
        full,
        linear,
        quadratic,
        approximation,
        linear_residual,
        residual,
        closure,
    )


@dataclass(frozen=True)
class StressAttributionPoint:
    shock_bps: int
    decomposition: SpotMoveAttribution


@dataclass(frozen=True)
class ResearchIvStressAttribution:
    version: str
    method: str
    source_study_fingerprint: str
    source_study_sha256: str
    source_scipy_version: str
    source_python_version: str
    attribution_python_version: str
    points: tuple[StressAttributionPoint, ...]
    evidence_fingerprint: str
    status: str = "computed_research_delta_gamma_attribution"
    decimal_profile: str = DECIMAL_PROFILE
    current_source_checked: bool = False
    approximation_accuracy_certified: bool = False
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


def attribute_research_iv_spot_stress(study: ResearchIvSpotStress) -> ResearchIvStressAttribution:
    """Untrusted pure transform. Structural/hash validation does not prove source/math truth."""
    from nse_quant.data_platform import research_iv_spot_stress as stress
    from nse_quant.data_platform import research_iv_stress_archive_record as record

    if (
        stress.VERSION != "research-iv-fixed-vol-spot-stress@1"
        or stress.MAX_SHOCKS != 16
        or stress.MAX_RESULT_BYTES != 65536
        or record.VERSION != "research-iv-spot-stress-archive-record@1"
        or record.MAX_STUDY_BYTES != stress.MAX_RESULT_BYTES
    ):
        raise ValueError("UNSUPPORTED_ATTRIBUTION_STUDY_PROFILE")
    if type(study) is not stress.ResearchIvSpotStress:
        raise ValueError("TYPED_RESEARCH_STRESS_STUDY_REQUIRED")
    shocks = stress.validate_shocks(study.shocks_bps)
    if (
        type(study.points) is not tuple
        or len(study.points) != len(shocks)
        or any(type(p) is not stress.SpotStressPoint for p in study.points)
    ):
        raise ValueError("ATTRIBUTION_IMMUTABLE_TYPED_SOURCE_POINTS_REQUIRED")
    raw = stress.canonical(asdict(study))
    if not 0 < len(raw) <= stress.MAX_RESULT_BYTES:
        raise ValueError("ATTRIBUTION_SOURCE_STUDY_BYTE_LIMIT")
    # Exact existing @1 codec helper: no copied BSM, study schema or native dependency.
    record._study(json.loads(raw), list(shocks))
    points: list[StressAttributionPoint] = []
    for shock, point in zip(shocks, study.points, strict=True):
        with localcontext(
            Context(prec=64, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999, clamp=0)
        ):
            expected_spot = stress.shocked_spot_decimal(study.spot_decimal, shock)
        if point.shocked_spot_decimal != expected_spot:
            raise ValueError("ATTRIBUTION_EXACT_SHOCK_COORDINATE_MISMATCH")
        part = decompose_spot_move(
            base_spot_decimal=study.spot_decimal,
            shocked_spot_decimal=point.shocked_spot_decimal,
            baseline_delta=study.baseline.delta,
            baseline_gamma=study.baseline.gamma,
            full_model_price_change=point.model_price_change,
        )
        points.append(StressAttributionPoint(shock, part))
    result = ResearchIvStressAttribution(
        VERSION,
        METHOD,
        study.evidence_fingerprint,
        hashlib.sha256(raw).hexdigest(),
        study.scipy_version,
        study.python_version,
        platform.python_version(),
        tuple(points),
        "",
    )
    fingerprint = hashlib.sha256(canonical(asdict(result))).hexdigest()
    result = replace(result, evidence_fingerprint=fingerprint)
    if len(canonical(asdict(result))) > MAX_ATTRIBUTION_BYTES:
        raise ValueError("ATTRIBUTION_RESULT_BYTE_LIMIT")
    return result
