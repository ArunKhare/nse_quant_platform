"""Plan-first read-only current revalidation inspection for an exact stress archive."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

VERSION = "research-iv-current-stress-archive-inspection@1"
SERVICE_VERSION = "research-iv-spot-stress-archive-current-revalidation@1"
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
    "archived_recording_verified",
    "current_source_checked",
    "model_computation_rechecked",
    "exact_recording_reproduced",
    "archive_unchanged_observed",
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


@contextmanager
def _open_inputs(paths: tuple[str, ...]) -> Iterator[tuple[Any, ...]]:
    """Only called by execute. Never create or initialize a missing database."""
    if type(paths) is not tuple or len(paths) != 7:
        raise ValueError("SEVEN_CURRENT_STRESS_DATABASE_ROLES_REQUIRED")
    files = tuple(Path(raw) for raw in paths)
    if any(not path.is_file() for path in files):
        raise ValueError("EXISTING_CURRENT_STRESS_DATABASES_REQUIRED")
    for role in (5, 6):
        if any(files[role].samefile(path) for path in files[:role]):
            raise ValueError("SEPARATE_CURRENT_STRESS_ARCHIVES_REQUIRED")
    import duckdb

    with ExitStack() as stack:
        opened: list[tuple[Path, Any]] = []
        handles: list[Any] = []
        for path in files:
            conn = next((c for previous, c in opened if path.samefile(previous)), None)
            if conn is None:
                conn = duckdb.connect(str(path), read_only=True)
                stack.callback(conn.close)
                opened.append((path, conn))
            handles.append(conn)
        yield tuple(handles)


def _study_metadata(value: Any) -> dict[str, Any]:
    from nse_quant.data_platform import research_iv_spot_stress as study_api

    if (
        study_api.VERSION != "research-iv-fixed-vol-spot-stress@1"
        or study_api.MAX_SHOCKS != 16
        or study_api.MAX_RESULT_BYTES != 65536
        or type(value) is not study_api.ResearchIvSpotStress
        or value.version != study_api.VERSION
        or value.status != "computed_fixed_iv_hypothetical_spot_stress"
        or not _pin(value.evidence_fingerprint)
        or value.current_source_checked is not False
        or any(
            getattr(value, k) is not False
            for k in DENIAL_FLAGS
            if k != "atomic_cross_database_snapshot_asserted"
        )
        or any(getattr(value, k) is not None for k in NULL_FIELDS)
    ):
        raise ValueError("CURRENT_STRESS_INSPECTION_STUDY_METADATA_CONTRACT")
    shocks = study_api.validate_shocks(value.shocks_bps)
    if len(study_api.canonical(asdict(value))) > study_api.MAX_RESULT_BYTES:
        raise ValueError("CURRENT_STRESS_INSPECTION_STUDY_BYTE_LIMIT")
    for version in (value.scipy_version, value.python_version):
        if type(version) is not str or re.fullmatch(r"[A-Za-z0-9.+_-]{1,64}", version) is None:
            raise ValueError("CURRENT_STRESS_INSPECTION_RUNTIME_PROFILE")
    return dict(
        study_fingerprint=value.evidence_fingerprint,
        study_version=value.version,
        shocks_bps=shocks,
        scipy_version=value.scipy_version,
        python_version=value.python_version,
    )


def _summary(result: Any, record_pin: str, fingerprint: str) -> tuple[str, int]:
    """Diagnostic projection only. Never expose provisional/retained replay payloads."""
    if (
        not _pin(record_pin)
        or not _pin(fingerprint)
        or result.version != SERVICE_VERSION
        or result.stress_record_id != record_pin
        or result.expected_recording_fingerprint != fingerprint
        or result.status
        not in (
            "matched_current_research_iv_spot_stress_archive",
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
        raise ValueError("CURRENT_STRESS_INSPECTION_RESULT_CONTRACT")
    if (
        result.current_source_checked
        and not result.archived_recording_verified
        or result.model_computation_rechecked
        and not result.current_source_checked
        or result.exact_recording_reproduced
        and not result.model_computation_rechecked
        or result.archive_unchanged_observed
        and not result.archived_recording_verified
    ):
        raise ValueError("CURRENT_STRESS_INSPECTION_INCONSISTENT_FACTS")
    positive = result.status == "matched_current_research_iv_spot_stress_archive"
    metadata = None
    if positive:
        if (
            not all(getattr(result, k) is True for k in OBSERVATION_FLAGS)
            or not _pin(result.native_stress_fingerprint)
            or not _pin(result.evidence_fingerprint)
            or result.study is None
        ):
            raise ValueError("CURRENT_STRESS_INSPECTION_INCOMPLETE_POSITIVE")
        metadata = _study_metadata(result.study)
    elif (
        result.study is not None
        or result.native_stress_fingerprint is not None
        or result.evidence_fingerprint is not None
    ):
        raise ValueError("CURRENT_STRESS_INSPECTION_REVIEW_CANNOT_EXPOSE_ACCEPTED_IDS")
    output = dict(
        inspection_version=VERSION,
        service_version=result.version,
        status=result.status,
        reason_codes=result.reason_codes,
        stress_record_id=record_pin,
        expected_recording_fingerprint=fingerprint,
        native_stress_fingerprint=result.native_stress_fingerprint,
        evidence_fingerprint=result.evidence_fingerprint,
        accepted_study_metadata=metadata,
        read_only_execution=True,
        **{k: getattr(result, k) for k in (*OBSERVATION_FLAGS, *DENIAL_FLAGS)},
        **dict.fromkeys(NULL_FIELDS),
    )
    raw = json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode()) > MAX_SUMMARY_BYTES:
        raise ValueError("CURRENT_STRESS_INSPECTION_SUMMARY_BYTE_LIMIT")
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
        parser.error(
            "Exact lowercase reviewed stress-record ID and full recording fingerprint required"
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
                        inputs_verified=False,
                        current_source_checked=False,
                        model_computation_rechecked=False,
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
            from nse_quant.data_platform import research_iv_stress_archive_revalidation as service

            if service.VERSION != SERVICE_VERSION or service.MAX_OBSERVATION_BYTES != 25165824:
                raise ValueError("CURRENT_STRESS_INSPECTION_UNSUPPORTED_SERVICE")
            result = service.revalidate_research_iv_spot_stress_archive(
                *handles,
                stress_record_id_pin=args.stress_record_id_pin,
                expected_recording_fingerprint=args.recording_fingerprint,
            )
            if type(result) is not service.ResearchIvCurrentStressArchive:
                raise ValueError("CURRENT_STRESS_INSPECTION_TYPED_RESULT_REQUIRED")
            raw, code = _summary(result, args.stress_record_id_pin, args.recording_fingerprint)
    except Exception:
        print(json.dumps(dict(status="FAILED", reason_code="IV_CURRENT_STRESS_INSPECTION_FAILED")))
        return 1
    print(raw)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
