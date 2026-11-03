"""Plan-first read-only native stress attribution diagnostics; not accuracy or P&L proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

VERSION = "research-iv-stress-attribution-inspection@1"
SERVICE_VERSION = "native-research-iv-stress-delta-gamma-attribution@1"
PATH_NAMES = (
    "bronze-db",
    "frame-silver-db",
    "reference-silver-db",
    "assessment-db",
    "source-gold-db",
    "archive-db",
    "stress-archive-db",
)
OBSERVATION_FLAGS = (
    "current_source_checked",
    "model_computation_rechecked",
    "current_context_matched",
    "attribution_reproduced",
)
DENIAL_FLAGS = (
    "approximation_accuracy_certified",
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


@contextmanager
def _open_inputs(paths: tuple[str, ...]) -> Iterator[tuple[Any, ...]]:
    if type(paths) is not tuple or len(paths) != 7:
        raise ValueError("SEVEN_ATTRIBUTION_DATABASE_ROLES_REQUIRED")
    files = tuple(Path(raw) for raw in paths)
    if any(not path.is_file() for path in files):
        raise ValueError("EXISTING_ATTRIBUTION_DATABASES_REQUIRED")
    for role in (5, 6):
        if any(files[role].samefile(path) for path in files[:role]):
            raise ValueError("SEPARATE_ATTRIBUTION_ARCHIVES_REQUIRED")
    import duckdb

    with ExitStack() as stack:
        opened: list[tuple[Path, Any]] = []
        handles: list[Any] = []
        for path in files:
            conn = next((c for prior, c in opened if path.samefile(prior)), None)
            if conn is None:
                conn = duckdb.connect(str(path), read_only=True)
                stack.callback(conn.close)
                opened.append((path, conn))
            handles.append(conn)
        yield tuple(handles)


def _attribution_payload(value: Any) -> dict[str, Any]:
    from nse_quant.data_platform import research_iv_stress_attribution as api

    if (
        api.VERSION != "research-iv-spot-stress-delta-gamma-attribution@1"
        or api.MAX_ATTRIBUTION_BYTES != 65536
        or api.METHOD != "baseline-delta-ds-plus-half-gamma-ds-squared@1"
        or api.DECIMAL_PROFILE != "precision64-half-even-emin-999999-emax999999-clamp0@1"
        or type(value) is not api.ResearchIvStressAttribution
        or value.version != api.VERSION
        or value.method != api.METHOD
        or value.decimal_profile != api.DECIMAL_PROFILE
        or value.status != "computed_research_delta_gamma_attribution"
        or value.current_source_checked is not False
        or any(getattr(value, k) is not False for k in DENIAL_FLAGS)
        or any(getattr(value, k) is not None for k in NULL_FIELDS)
        or not all(
            _pin(getattr(value, k))
            for k in (
                "source_study_fingerprint",
                "source_study_sha256",
                "evidence_fingerprint",
            )
        )
        or type(value.points) is not tuple
        or not 1 <= len(value.points) <= 16
    ):
        raise ValueError("ATTRIBUTION_INSPECTION_ACCEPTED_PAYLOAD_CONTRACT")
    raw = api.canonical(asdict(value))
    if len(raw) > api.MAX_ATTRIBUTION_BYTES:
        raise ValueError("ATTRIBUTION_INSPECTION_PAYLOAD_BYTE_LIMIT")
    unsigned = api.canonical(asdict(replace(value, evidence_fingerprint="")))
    expected = hashlib.sha256(unsigned).hexdigest()
    if value.evidence_fingerprint != expected:
        raise ValueError("ATTRIBUTION_INSPECTION_PAYLOAD_FINGERPRINT_MISMATCH")
    for label in (
        value.source_scipy_version,
        value.source_python_version,
        value.attribution_python_version,
    ):
        if type(label) is not str or re.fullmatch(r"[A-Za-z0-9.+_-]{1,64}", label) is None:
            raise ValueError("ATTRIBUTION_INSPECTION_RUNTIME_PROFILE")
    shocks = tuple(p.shock_bps for p in value.points)
    if any(type(x) is not int or not -5000 <= x <= 5000 for x in shocks) or shocks != tuple(
        sorted(set(shocks))
    ):
        raise ValueError("ATTRIBUTION_INSPECTION_POINT_SCOPE")
    projected: list[dict[str, Any]] = []
    for point in value.points:
        if type(point) is not api.StressAttributionPoint:
            raise ValueError("ATTRIBUTION_INSPECTION_TYPED_POINT_REQUIRED")
        part = point.decomposition
        if type(part) is not api.SpotMoveAttribution:
            raise ValueError("ATTRIBUTION_INSPECTION_TYPED_DECOMPOSITION_REQUIRED")
        for name, scalar in asdict(part).items():
            if name.endswith("_decimal"):
                if type(scalar) is not str or len(scalar) > 48:
                    raise ValueError("ATTRIBUTION_INSPECTION_DECIMAL_PROFILE")
            elif type(scalar) not in (int, float) or not math.isfinite(scalar):
                raise ValueError("ATTRIBUTION_INSPECTION_NONFINITE_SCALAR")
        # No repricing, residual threshold, correction-to-zero or rounded projection.
        projected.append(
            dict(
                shock_bps=point.shock_bps,
                spot_change_decimal=part.spot_change_decimal,
                full_model_price_change=part.full_model_price_change,
                delta_component=part.delta_component,
                gamma_component=part.gamma_component,
                delta_gamma_approximation=part.delta_gamma_approximation,
                delta_only_residual=part.delta_only_residual,
                second_order_residual=part.second_order_residual,
                reconstruction_roundoff=part.reconstruction_roundoff,
            )
        )
    return dict(
        version=value.version,
        method=value.method,
        decimal_profile=value.decimal_profile,
        attribution_fingerprint=value.evidence_fingerprint,
        source_study_fingerprint=value.source_study_fingerprint,
        source_study_sha256=value.source_study_sha256,
        source_scipy_version=value.source_scipy_version,
        source_python_version=value.source_python_version,
        attribution_python_version=value.attribution_python_version,
        points=projected,
    )


def _summary(value: Any, record_pin: str, fingerprint: str) -> tuple[str, int]:
    if (
        not _pin(record_pin)
        or not _pin(fingerprint)
        or value.version != SERVICE_VERSION
        or value.stress_record_id != record_pin
        or value.expected_recording_fingerprint != fingerprint
        or value.status
        not in (
            "computed_current_native_research_iv_stress_attribution",
            "review_required",
        )
        or any(type(getattr(value, k)) is not bool for k in OBSERVATION_FLAGS)
        or any(getattr(value, k) is not False for k in DENIAL_FLAGS)
        or any(getattr(value, k) is not None for k in NULL_FIELDS)
        or type(value.reason_codes) is not tuple
        or not 1 <= len(value.reason_codes) <= 16
        or any(
            type(c) is not str or re.fullmatch(r"[A-Z0-9_]{1,128}", c) is None
            for c in value.reason_codes
        )
        or len(set(value.reason_codes)) != len(value.reason_codes)
    ):
        raise ValueError("ATTRIBUTION_INSPECTION_NATIVE_CONTRACT_MISMATCH")
    if (
        value.model_computation_rechecked
        and not value.current_source_checked
        or value.current_context_matched
        and not value.model_computation_rechecked
        or value.attribution_reproduced
        and not value.current_context_matched
    ):
        raise ValueError("ATTRIBUTION_INSPECTION_INCONSISTENT_FACTS")
    positive = value.status == "computed_current_native_research_iv_stress_attribution"
    accepted = None
    if positive:
        if (
            not all(getattr(value, k) is True for k in OBSERVATION_FLAGS)
            or not _pin(value.evidence_fingerprint)
            or value.attribution is None
            or value.attribution != value.provisional_attribution
            or value.attribution != value.repeated_attribution
        ):
            raise ValueError("ATTRIBUTION_INSPECTION_INCOMPLETE_POSITIVE")
        accepted = _attribution_payload(value.attribution)
    elif value.attribution is not None or value.evidence_fingerprint is not None:
        raise ValueError("ATTRIBUTION_INSPECTION_REVIEW_CANNOT_EXPOSE_ACCEPTED_OUTPUT")
    result = dict(
        inspection_version=VERSION,
        service_version=value.version,
        status=value.status,
        reason_codes=value.reason_codes,
        stress_record_id=record_pin,
        expected_recording_fingerprint=fingerprint,
        evidence_fingerprint=value.evidence_fingerprint,
        accepted_attribution=accepted,
        read_only_execution=True,
        **{k: getattr(value, k) for k in (*OBSERVATION_FLAGS, *DENIAL_FLAGS)},
        **dict.fromkeys(NULL_FIELDS),
    )
    raw = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode()) > MAX_SUMMARY_BYTES:
        raise ValueError("ATTRIBUTION_INSPECTION_SUMMARY_BYTE_LIMIT")
    return raw, 0 if positive else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in PATH_NAMES:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--stress-record-id-pin", required=True)
    parser.add_argument("--recording-fingerprint", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not _pin(args.stress_record_id_pin) or not _pin(args.recording_fingerprint):
        parser.error("Exact lowercase reviewed stress record ID and recording fingerprint required")
    paths = tuple(getattr(args, name.replace("-", "_")) for name in PATH_NAMES)
    if any(not 0 < len(p) <= 4096 or any(ord(c) < 32 for c in p) for p in paths):
        parser.error("Bounded nonempty literal database paths required")
    if not args.execute:
        print(
            json.dumps(
                dict(
                    status="PLANNED",
                    plan=dict(
                        inspection_version=VERSION,
                        service_version=SERVICE_VERSION,
                        paths_as_supplied=dict(zip(PATH_NAMES, paths, strict=True)),
                        stress_record_id_pin=args.stress_record_id_pin,
                        expected_recording_fingerprint=args.recording_fingerprint,
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
            from nse_quant.data_platform import native_research_iv_stress_attribution as native

            if native.VERSION != SERVICE_VERSION or native.MAX_CONTEXT_BYTES != 167772160:
                raise ValueError("ATTRIBUTION_INSPECTION_UNSUPPORTED_NATIVE_PROFILE")
            value = native.build_native_research_iv_stress_attribution(
                *handles,
                stress_record_id_pin=args.stress_record_id_pin,
                expected_recording_fingerprint=args.recording_fingerprint,
            )
            if type(value) is not native.NativeResearchIvStressAttribution:
                raise ValueError("ATTRIBUTION_INSPECTION_TYPED_NATIVE_RESULT_REQUIRED")
            raw, code = _summary(value, args.stress_record_id_pin, args.recording_fingerprint)
    except Exception:
        print(
            json.dumps(
                dict(
                    status="FAILED",
                    reason_code="IV_STRESS_ATTRIBUTION_INSPECTION_FAILED",
                )
            )
        )
        return 1
    print(raw)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
