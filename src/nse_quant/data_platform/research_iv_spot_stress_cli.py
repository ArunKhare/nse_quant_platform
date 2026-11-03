"""Plan-first read-only native fixed-IV spot-stress inspection; not portfolio P&L."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

VERSION = "research-iv-spot-stress-inspection@1"
SERVICE_VERSION = "native-research-iv-fixed-vol-spot-stress@1"
PATH_NAMES = (
    "bronze-db",
    "frame-silver-db",
    "reference-silver-db",
    "assessment-db",
    "source-gold-db",
    "archive-db",
)
OBSERVATION_FLAGS = (
    "current_source_checked",
    "exact_native_observations_matched",
    "stress_results_reproduced",
)
DENIAL_FLAGS = (
    "portfolio_pnl_asserted",
    "volatility_response_modelled",
    "option_underlying_identity_binding_verified",
    "scenario_terms_authoritative",
    "model_suitability_verified",
    "source_acquisition_authenticity_asserted",
    "availability_evidence_verified",
    "historical_validity_asserted",
    "publication_asserted",
    "decision_eligibility_asserted",
    "atomic_cross_database_snapshot_asserted",
)
NULL_FIELDS = ("canonical_contract_id", "event_ts", "published_at")
MAX_SUMMARY_BYTES = 16384


def _pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _shocks(values: list[str]) -> tuple[int, ...]:
    if not 1 <= len(values) <= 16 or any(
        re.fullmatch(r"(?:0|-?[1-9][0-9]{0,3})", value) is None for value in values
    ):
        raise ValueError("BOUNDED_CANONICAL_INTEGER_SHOCKS_REQUIRED")
    result = tuple(int(value) for value in values)
    if result != tuple(sorted(set(result))) or any(not -5000 <= v <= 5000 for v in result):
        raise ValueError("SORTED_UNIQUE_SHOCKS_WITHIN_PROFILE_REQUIRED")
    return result


@contextmanager
def _open_inputs(paths: tuple[str, ...]) -> Iterator[tuple[Any, ...]]:
    if type(paths) is not tuple or len(paths) != 6:
        raise ValueError("SIX_STRESS_DATABASE_ROLES_REQUIRED")
    files = tuple(Path(raw) for raw in paths)
    if any(not path.is_file() for path in files):
        raise ValueError("EXISTING_STRESS_DATABASES_REQUIRED")
    if any(files[5].samefile(path) for path in files[:5]):
        raise ValueError("SEPARATE_STRESS_ARCHIVE_REQUIRED")
    import duckdb

    with ExitStack() as stack:
        opened: list[tuple[Path, Any]] = []
        handles: list[Any] = []
        for path in files:
            conn = next((conn for previous, conn in opened if path.samefile(previous)), None)
            if conn is None:
                conn = duckdb.connect(str(path), read_only=True)
                stack.callback(conn.close)
                opened.append((path, conn))
            handles.append(conn)
        yield tuple(handles)


def _study_payload(study: Any, shocks: tuple[int, ...]) -> dict[str, Any]:
    from nse_quant.data_platform import research_iv_spot_stress as stress
    from nse_quant.data_platform import research_option_model as model

    if (
        type(study) is not stress.ResearchIvSpotStress
        or study.version != "research-iv-fixed-vol-spot-stress@1"
        or stress.MAX_SHOCKS != 16
        or stress.MAX_RESULT_BYTES != 65536
        or study.model_version != model.VERSION
        or model.VERSION != "research-european-bsm-iv@1"
        or study.status != "computed_fixed_iv_hypothetical_spot_stress"
        or study.shocks_bps != shocks
        or type(study.shocks_bps) is not tuple
        or type(study.points) is not tuple
        or len(study.points) != len(shocks)
        or not _pin(study.evidence_fingerprint)
        or study.current_source_checked is not False
        or any(
            getattr(study, key) is not False
            for key in DENIAL_FLAGS
            if key != "atomic_cross_database_snapshot_asserted"
        )
        or any(getattr(study, key) is not None for key in NULL_FIELDS)
        or type(study.fixed_implied_volatility) is not float
        or not math.isfinite(study.fixed_implied_volatility)
        or not 0.000001 <= study.fixed_implied_volatility <= 5.0
    ):
        raise ValueError("STRESS_INSPECTION_STUDY_CONTRACT_MISMATCH")
    model.scenario_terms_sha256(study.terms)
    for version in (study.scipy_version, study.python_version):
        if type(version) is not str or re.fullmatch(r"[A-Za-z0-9.+_-]{1,64}", version) is None:
            raise ValueError("STRESS_INSPECTION_RUNTIME_CONTEXT_REQUIRED")

    def values(value: Any) -> dict[str, Any]:
        if type(value) is not model.BsmValues:
            raise ValueError("STRESS_INSPECTION_TYPED_MODEL_VALUES_REQUIRED")
        result = asdict(value)
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in result.values()):
            raise ValueError("STRESS_INSPECTION_FINITE_MODEL_VALUES_REQUIRED")
        if value.price < 0 or value.gamma < 0 or value.vega_per_vol_unit < 0:
            raise ValueError("STRESS_INSPECTION_NONNEGATIVE_MODEL_FIELDS_REQUIRED")
        return result

    baseline = values(study.baseline)
    points: list[dict[str, Any]] = []
    for point, shock in zip(study.points, shocks, strict=True):
        if (
            type(point) is not stress.SpotStressPoint
            or type(point.shock_bps) is not int
            or point.shock_bps != shock
            or type(point.shocked_spot_decimal) is not str
            or re.fullmatch(r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,16})?", point.shocked_spot_decimal)
            is None
            or type(point.model_price_change) not in (int, float)
            or not math.isfinite(point.model_price_change)
            or point.model_price_change != point.values.price - study.baseline.price
        ):
            raise ValueError("STRESS_INSPECTION_POINT_CONTRACT_MISMATCH")
        points.append(
            dict(
                shock_bps=shock,
                shocked_spot_decimal=point.shocked_spot_decimal,
                values=values(point.values),
                model_price_change=point.model_price_change,
            )
        )
    if len(stress.canonical(asdict(study))) > stress.MAX_RESULT_BYTES:
        raise ValueError("STRESS_INSPECTION_STUDY_BYTE_LIMIT")
    return dict(
        version=study.version,
        study_fingerprint=study.evidence_fingerprint,
        fixed_implied_volatility=study.fixed_implied_volatility,
        scipy_version=study.scipy_version,
        python_version=study.python_version,
        baseline=baseline,
        points=points,
    )


def _summary(result: Any, pins: tuple[str, str, str], shocks: tuple[int, ...]) -> tuple[str, int]:
    if (
        result.version != SERVICE_VERSION
        or (
            result.build_id,
            result.expected_archive_fingerprint,
            result.expected_revalidation_fingerprint,
        )
        != pins
        or result.status
        not in (
            "computed_current_native_research_iv_spot_stress",
            "review_required",
        )
        or any(type(getattr(result, k)) is not bool for k in OBSERVATION_FLAGS)
        or any(getattr(result, k) is not False for k in DENIAL_FLAGS)
        or any(getattr(result, k) is not None for k in NULL_FIELDS)
        or type(result.reason_codes) is not tuple
        or not 1 <= len(result.reason_codes) <= 16
        or any(
            type(c) is not str or re.fullmatch(r"[A-Z0-9_]{1,128}", c) is None
            for c in result.reason_codes
        )
        or len(set(result.reason_codes)) != len(result.reason_codes)
    ):
        raise ValueError("STRESS_INSPECTION_RESULT_CONTRACT_MISMATCH")
    positive = result.status == "computed_current_native_research_iv_spot_stress"
    curve = None
    if positive:
        if (
            not all(getattr(result, k) is True for k in OBSERVATION_FLAGS)
            or not _pin(result.evidence_fingerprint)
            or result.study is None
        ):
            raise ValueError("STRESS_INSPECTION_INCOMPLETE_POSITIVE")
        if result.study != result.provisional_study or result.study != result.repeated_study:
            raise ValueError("STRESS_INSPECTION_UNREPRODUCED_ACCEPTED_STUDY")
        curve = _study_payload(result.study, shocks)
    elif result.study is not None or result.evidence_fingerprint is not None:
        raise ValueError("STRESS_INSPECTION_REVIEW_CANNOT_EXPOSE_ACCEPTED_STUDY")
    output = dict(
        inspection_version=VERSION,
        service_version=result.version,
        status=result.status,
        reason_codes=result.reason_codes,
        build_id=pins[0],
        expected_archive_fingerprint=pins[1],
        expected_revalidation_fingerprint=pins[2],
        shocks_bps=shocks,
        evidence_fingerprint=result.evidence_fingerprint,
        accepted_study=curve,
        read_only_execution=True,
        **{k: getattr(result, k) for k in (*OBSERVATION_FLAGS, *DENIAL_FLAGS)},
        **dict.fromkeys(NULL_FIELDS),
    )
    raw = json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode()) > MAX_SUMMARY_BYTES:
        raise ValueError("STRESS_INSPECTION_SUMMARY_BYTE_LIMIT")
    return raw, 0 if positive else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in PATH_NAMES:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--build-id-pin", required=True)
    parser.add_argument("--archive-fingerprint", required=True)
    parser.add_argument("--revalidation-fingerprint", required=True)
    parser.add_argument("--shock-bps", action="append", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    pins = (args.build_id_pin, args.archive_fingerprint, args.revalidation_fingerprint)
    if not all(_pin(p) for p in pins):
        parser.error("Exact lowercase reviewed build/archive/native revalidation pins required")
    try:
        shocks = _shocks(args.shock_bps)
    except ValueError:
        parser.error("1..16 sorted unique canonical integer shocks in -5000..5000 required")
    paths = tuple(getattr(args, name.replace("-", "_")) for name in PATH_NAMES)
    if any(not 0 < len(p) <= 4096 or any(ord(c) < 32 for c in p) for p in paths):
        parser.error("Bounded nonempty database path strings required")
    if not args.execute:
        print(
            json.dumps(
                dict(
                    status="PLANNED",
                    plan=dict(
                        inspection_version=VERSION,
                        service_version=SERVICE_VERSION,
                        paths_as_supplied=dict(zip(PATH_NAMES, paths, strict=True)),
                        build_id_pin=pins[0],
                        expected_archive_fingerprint=pins[1],
                        expected_revalidation_fingerprint=pins[2],
                        shocks_bps=shocks,
                        inputs_verified=False,
                        current_source_checked=False,
                        read_only_execution=True,
                        **dict.fromkeys(DENIAL_FLAGS, False),
                    ),
                ),
                sort_keys=True,
            )
        )
        return 0
    try:
        with _open_inputs(paths) as handles:
            from nse_quant.data_platform import native_research_iv_spot_stress as service

            if service.VERSION != SERVICE_VERSION or service.MAX_NATIVE_BYTES != 8388608:
                raise ValueError("STRESS_INSPECTION_UNSUPPORTED_NATIVE_PROFILE")
            result = service.build_native_research_iv_spot_stress(
                *handles,
                build_id_pin=pins[0],
                expected_archive_fingerprint=pins[1],
                expected_revalidation_fingerprint=pins[2],
                shocks_bps=shocks,
            )
            if type(result) is not service.NativeResearchIvSpotStress:
                raise ValueError("STRESS_INSPECTION_TYPED_NATIVE_RESULT_REQUIRED")
            raw, code = _summary(result, pins, shocks)
    except Exception:
        print(json.dumps(dict(status="FAILED", reason_code="IV_SPOT_STRESS_INSPECTION_FAILED")))
        return 1
    print(raw)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
