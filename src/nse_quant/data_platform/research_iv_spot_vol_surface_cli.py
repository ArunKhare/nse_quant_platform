"""Plan-first read-only hypothetical spot-vol surface inspection; not market response/P&L."""

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

VERSION = "research-iv-spot-vol-surface-inspection@1"
SERVICE_VERSION = "native-research-iv-hypothetical-spot-vol-surface@1"
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
    "surface_reproduced",
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


def _vol_shifts(values: list[str]) -> tuple[int, ...]:
    if not 1 <= len(values) <= 8 or any(
        re.fullmatch(r"(?:0|-?[1-9][0-9]{0,3})", v) is None for v in values
    ):
        raise ValueError("CANONICAL_BOUNDED_ABSOLUTE_VOL_SHIFT_TOKENS_REQUIRED")
    result = tuple(int(v) for v in values)
    if result != tuple(sorted(set(result))) or any(not -5000 <= v <= 5000 for v in result):
        raise ValueError("SORTED_UNIQUE_ABSOLUTE_VOL_SHIFTS_REQUIRED")
    return result


@contextmanager
def _open_inputs(paths: tuple[str, ...]) -> Iterator[tuple[Any, ...]]:
    if type(paths) is not tuple or len(paths) != 7:
        raise ValueError("SEVEN_SURFACE_DATABASE_ROLES_REQUIRED")
    files = tuple(Path(raw) for raw in paths)
    if any(not path.is_file() for path in files):
        raise ValueError("EXISTING_SURFACE_DATABASES_REQUIRED")
    for role in (5, 6):
        if any(files[role].samefile(path) for path in files[:role]):
            raise ValueError("SEPARATE_SURFACE_ARCHIVES_REQUIRED")
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


def _range_metrics(rows: tuple[tuple[float, float, float], ...]) -> dict[str, float]:
    """Finite min/max selectors over complete per-column rows, never pricing or risk proof."""
    if (
        type(rows) is not tuple
        or not 1 <= len(rows) <= 16
        or any(type(r) is not tuple or len(r) != 3 for r in rows)
        or any(type(v) not in (int, float) or not math.isfinite(v) for r in rows for v in r)
    ):
        raise ValueError("SURFACE_INSPECTION_COMPLETE_FINITE_METRIC_ROWS_REQUIRED")
    return dict(
        full_model_price_change_min=min(r[0] for r in rows),
        full_model_price_change_max=max(r[0] for r in rows),
        interaction_change_min=min(r[1] for r in rows),
        interaction_change_max=max(r[1] for r in rows),
        reconstruction_roundoff_abs_max=max(abs(r[2]) for r in rows),
    )


def _surface_payload(value: Any, shifts: tuple[int, ...]) -> dict[str, Any]:
    from nse_quant.data_platform import research_iv_spot_vol_surface as api
    from nse_quant.data_platform import research_option_model as model

    if (
        api.VERSION != "research-iv-hypothetical-spot-vol-surface@1"
        or api.MAX_VOL_SHIFTS != 8
        or api.MAX_CELLS != 128
        or api.MAX_SURFACE_BYTES != 262144
        or api.VOL_PROFILE != ("binary-float-exact-decimal-plus-bps-over-10000-prec128-half-even@1")
        or model.VERSION != "research-european-bsm-iv@1"
        or type(value) is not api.ResearchIvSpotVolSurface
        or value.version != api.VERSION
        or value.model_version != model.VERSION
        or value.volatility_profile != api.VOL_PROFILE
        or value.status != "computed_hypothetical_spot_vol_surface"
        or value.vol_shifts_bps != shifts
        or type(value.vol_shifts_bps) is not tuple
        or value.hypothetical_volatility_shift_assumed is not True
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
        or type(value.spot_shocks_bps) is not tuple
        or not 1 <= len(value.spot_shocks_bps) <= 16
        or any(type(s) is not int or not -5000 <= s <= 5000 for s in value.spot_shocks_bps)
        or value.spot_shocks_bps != tuple(sorted(set(value.spot_shocks_bps)))
        or type(value.columns) is not tuple
        or len(value.columns) != len(shifts)
        or type(value.cells) is not tuple
        or len(value.cells) != len(value.spot_shocks_bps) * len(shifts)
        or len(value.cells) > api.MAX_CELLS
        or type(value.base_volatility) is not float
        or not math.isfinite(value.base_volatility)
        or value.base_volatility_hex != value.base_volatility.hex()
    ):
        raise ValueError("SURFACE_INSPECTION_ACCEPTED_PAYLOAD_CONTRACT")
    api.validate_vol_shifts(shifts)
    raw = api.canonical(asdict(value))
    if len(raw) > api.MAX_SURFACE_BYTES:
        raise ValueError("SURFACE_INSPECTION_PAYLOAD_BYTE_LIMIT")
    unsigned = api.canonical(asdict(replace(value, evidence_fingerprint="")))
    if hashlib.sha256(unsigned).hexdigest() != value.evidence_fingerprint:
        raise ValueError("SURFACE_INSPECTION_PAYLOAD_FINGERPRINT_MISMATCH")
    for version in (value.scipy_version, value.python_version):
        if type(version) is not str or re.fullmatch(r"[A-Za-z0-9.+_-]{1,64}", version) is None:
            raise ValueError("SURFACE_INSPECTION_RUNTIME_PROFILE")

    def finite_model_values(data: Any) -> None:
        if type(data) is not model.BsmValues:
            raise ValueError("SURFACE_INSPECTION_TYPED_MODEL_VALUES_REQUIRED")
        if (
            any(type(v) not in (int, float) or not math.isfinite(v) for v in asdict(data).values())
            or data.price < 0
            or data.gamma < 0
            or data.vega_per_vol_unit < 0
        ):
            raise ValueError("SURFACE_INSPECTION_FINITE_MODEL_VALUES_REQUIRED")

    finite_model_values(value.baseline)
    model.scenario_terms_sha256(value.terms)
    expected_cells = [(spot, vol) for spot in value.spot_shocks_bps for vol in shifts]
    grouped: dict[int, list[tuple[float, float, float]]] = {v: [] for v in shifts}
    for cell, scope in zip(value.cells, expected_cells, strict=True):
        if (
            type(cell) is not api.SpotVolCell
            or type(cell.spot_shock_bps) is not int
            or type(cell.vol_shift_bps) is not int
            or (cell.spot_shock_bps, cell.vol_shift_bps) != scope
        ):
            raise ValueError("SURFACE_INSPECTION_FULL_CARTESIAN_GRID_REQUIRED")
        finite_model_values(cell.values)
        metrics = (
            cell.full_model_price_change,
            cell.spot_only_change,
            cell.vol_only_change,
            cell.interaction_change,
            cell.reconstruction_roundoff,
        )
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in metrics):
            raise ValueError("SURFACE_INSPECTION_FINITE_CELL_METRICS_REQUIRED")
        grouped[cell.vol_shift_bps].append(
            (cell.full_model_price_change, cell.interaction_change, cell.reconstruction_roundoff)
        )
    columns: list[dict[str, Any]] = []
    for column, shift in zip(value.columns, shifts, strict=True):
        if (
            type(column) is not api.SurfaceVolColumn
            or type(column.volatility) is not api.ShiftedVolatility
        ):
            raise ValueError("SURFACE_INSPECTION_TYPED_COLUMN_REQUIRED")
        # Actual coordinate helper verifies decimal/float/hex consistency, not price/model truth.
        if column.volatility != api.shifted_volatility(value.base_volatility, shift):
            raise ValueError("SURFACE_INSPECTION_EXACT_VOL_COORDINATE_MISMATCH")
        finite_model_values(column.base_spot_values)
        columns.append(
            dict(
                shift_bps=shift,
                exact_volatility_decimal=column.volatility.exact_decimal,
                volatility=column.volatility.value,
                volatility_hex=column.volatility.value_hex,
                **_range_metrics(tuple(grouped[shift])),
            )
        )
    return dict(
        version=value.version,
        surface_fingerprint=value.evidence_fingerprint,
        source_study_fingerprint=value.source_study_fingerprint,
        source_study_sha256=value.source_study_sha256,
        volatility_profile=value.volatility_profile,
        base_volatility=value.base_volatility,
        base_volatility_hex=value.base_volatility_hex,
        spot_shocks_bps=value.spot_shocks_bps,
        vol_shifts_bps=shifts,
        cell_count=len(value.cells),
        scipy_version=value.scipy_version,
        python_version=value.python_version,
        column_summaries=columns,
    )


def _summary(
    value: Any, record_pin: str, fingerprint: str, shifts: tuple[int, ...]
) -> tuple[str, int]:
    if (
        not _pin(record_pin)
        or not _pin(fingerprint)
        or value.version != SERVICE_VERSION
        or value.stress_record_id != record_pin
        or value.expected_recording_fingerprint != fingerprint
        or value.vol_shifts_bps != shifts
        or type(value.vol_shifts_bps) is not tuple
        or value.hypothetical_volatility_shift_assumed is not True
        or value.status
        not in (
            "computed_current_native_research_iv_spot_vol_surface",
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
        raise ValueError("SURFACE_INSPECTION_NATIVE_RESULT_CONTRACT")
    if (
        value.model_computation_rechecked
        and not value.current_source_checked
        or value.current_context_matched
        and not value.model_computation_rechecked
        or value.surface_reproduced
        and not value.current_context_matched
    ):
        raise ValueError("SURFACE_INSPECTION_INCONSISTENT_FACTS")
    positive = value.status == "computed_current_native_research_iv_spot_vol_surface"
    accepted = None
    if positive:
        if (
            not all(getattr(value, k) is True for k in OBSERVATION_FLAGS)
            or not _pin(value.evidence_fingerprint)
            or value.surface is None
            or value.surface != value.provisional_surface
            or value.surface != value.repeated_surface
        ):
            raise ValueError("SURFACE_INSPECTION_INCOMPLETE_POSITIVE")
        accepted = _surface_payload(value.surface, shifts)
    elif value.surface is not None or value.evidence_fingerprint is not None:
        raise ValueError("SURFACE_INSPECTION_REVIEW_CANNOT_EXPOSE_ACCEPTED_OUTPUT")
    output = dict(
        inspection_version=VERSION,
        service_version=value.version,
        status=value.status,
        reason_codes=value.reason_codes,
        stress_record_id=record_pin,
        expected_recording_fingerprint=fingerprint,
        vol_shifts_bps=shifts,
        vol_shift_units="ABSOLUTE_ANNUAL_SIGMA_BASIS_POINTS",
        hypothetical_volatility_shift_assumed=True,
        evidence_fingerprint=value.evidence_fingerprint,
        accepted_surface_summary=accepted,
        read_only_execution=True,
        **{k: getattr(value, k) for k in (*OBSERVATION_FLAGS, *DENIAL_FLAGS)},
        **dict.fromkeys(NULL_FIELDS),
    )
    raw = json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode()) > MAX_SUMMARY_BYTES:
        raise ValueError("SURFACE_INSPECTION_SUMMARY_BYTE_LIMIT")
    return raw, 0 if positive else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in PATH_NAMES:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--stress-record-id-pin", required=True)
    parser.add_argument("--recording-fingerprint", required=True)
    parser.add_argument("--vol-shift-bps", action="append", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not _pin(args.stress_record_id_pin) or not _pin(args.recording_fingerprint):
        parser.error(
            "Exact lowercase reviewed stress record ID and full recording fingerprint required"
        )
    try:
        shifts = _vol_shifts(args.vol_shift_bps)
    except ValueError:
        parser.error(
            "1..8 sorted unique canonical absolute-vol basis-point shifts in -5000..5000 required"
        )
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
                        vol_shifts_bps=shifts,
                        vol_shift_units="ABSOLUTE_ANNUAL_SIGMA_BASIS_POINTS",
                        hypothetical_volatility_shift_assumed=True,
                        derived_coordinates_checked=False,
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
            from nse_quant.data_platform import native_research_iv_spot_vol_surface as native

            if native.VERSION != SERVICE_VERSION or native.MAX_CONTEXT_BYTES != 167772160:
                raise ValueError("SURFACE_INSPECTION_UNSUPPORTED_NATIVE_PROFILE")
            value = native.build_native_research_iv_spot_vol_surface(
                *handles,
                stress_record_id_pin=args.stress_record_id_pin,
                expected_recording_fingerprint=args.recording_fingerprint,
                vol_shifts_bps=shifts,
            )
            if type(value) is not native.NativeResearchIvSpotVolSurface:
                raise ValueError("SURFACE_INSPECTION_TYPED_NATIVE_RESULT_REQUIRED")
            raw, code = _summary(
                value,
                args.stress_record_id_pin,
                args.recording_fingerprint,
                shifts,
            )
    except Exception:
        print(
            json.dumps(
                dict(
                    status="FAILED",
                    reason_code="IV_SPOT_VOL_SURFACE_INSPECTION_FAILED",
                )
            )
        )
        return 1
    print(raw)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
