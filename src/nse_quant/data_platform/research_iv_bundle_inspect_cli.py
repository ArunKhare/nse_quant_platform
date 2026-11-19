"""Plan-first, bounded read-only inspection of an exact archived research-IV bundle."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

VERSION = "research-iv-bundle-inspection@1"
SERVICE_VERSION = "research-iv-bundle-current-source-revalidation@1"
PATH_NAMES = (
    "bronze-db",
    "frame-silver-db",
    "reference-silver-db",
    "assessment-db",
    "source-gold-db",
    "archive-db",
    "bundle-archive-db",
)
OBSERVATION_FLAGS = (
    "archived_recording_verified",
    "current_source_checked",
    "exact_recording_reproduced",
    "archive_unchanged_observed",
    "all_members_revalidated",
)
DENIAL_FLAGS = (
    "publication_asserted",
    "availability_evidence_verified",
    "historical_validity_asserted",
    "option_underlying_identity_binding_verified",
    "scenario_terms_authoritative",
    "model_suitability_verified",
    "source_acquisition_authenticity_asserted",
    "atomic_cross_database_snapshot_asserted",
    "decision_eligibility_asserted",
)
MAX_SUMMARY_BYTES = 16384


def _pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


@contextmanager
def _open_inputs(paths: tuple[str, ...]) -> Iterator[tuple[Any, ...]]:
    """Execution only. Never initialize. Reuse one handle per supported physical source."""
    if len(paths) != 7:
        raise ValueError("SEVEN_EXISTING_IV_BUNDLE_DATABASES_REQUIRED")
    files = tuple(Path(raw) for raw in paths)
    if any(not path.is_file() for path in files):
        raise ValueError("EXISTING_IV_BUNDLE_INPUT_DATABASES_REQUIRED")
    if any(files[6].samefile(path) for path in files[:6]):
        raise ValueError("SEPARATE_IV_BUNDLE_ARCHIVE_REQUIRED")
    if any(files[5].samefile(path) for path in files[:5]):
        raise ValueError("SEPARATE_IV_MEMBER_ARCHIVE_REQUIRED")
    import duckdb

    with ExitStack() as stack:
        opened: list[tuple[Path, Any]] = []
        handles: list[Any] = []
        for path in files:
            conn = next((conn for old, conn in opened if path.samefile(old)), None)
            if conn is None:
                conn = duckdb.connect(str(path), read_only=True)
                stack.callback(conn.close)
                opened.append((path, conn))
            handles.append(conn)
        yield tuple(handles)


def _summary(result: Any, build_pin: str, archive_pin: str) -> tuple[str, int]:
    """Diagnostic projection only; never emit nested artifacts or exception messages."""
    if (
        result.version != SERVICE_VERSION
        or result.build_id != build_pin
        or result.expected_archive_fingerprint != archive_pin
        or result.status not in ("review_required", "matched_current_research_iv_bundle")
        or any(type(getattr(result, name)) is not bool for name in OBSERVATION_FLAGS)
        or any(getattr(result, name) is not False for name in DENIAL_FLAGS)
        or result.canonical_contract_id is not None
        or type(result.reason_codes) is not tuple
        or not 1 <= len(result.reason_codes) <= 64
        or any(
            not isinstance(code, str) or re.fullmatch(r"[A-Z0-9_]{1,128}", code) is None
            for code in result.reason_codes
        )
        or len(set(result.reason_codes)) != len(result.reason_codes)
    ):
        raise ValueError("IV_BUNDLE_INSPECTION_RESULT_CONTRACT_MISMATCH")
    positive = result.status == "matched_current_research_iv_bundle"
    if positive:
        if (
            not all(getattr(result, name) is True for name in OBSERVATION_FLAGS)
            or not _pin(result.bundle_id)
            or not _pin(result.evidence_fingerprint)
        ):
            raise ValueError("IV_BUNDLE_INSPECTION_INCOMPLETE_POSITIVE_RESULT")
    elif (
        result.exact_recording_reproduced is not False
        or result.all_members_revalidated is not False
        or result.bundle_id is not None
        or result.evidence_fingerprint is not None
    ):
        raise ValueError("IV_BUNDLE_INSPECTION_REVIEW_CANNOT_REPORT_ACCEPTED_BUNDLE")
    value = {
        "inspection_version": VERSION,
        "service_version": result.version,
        "status": result.status,
        "reason_codes": result.reason_codes,
        "build_id": result.build_id,
        "expected_archive_fingerprint": archive_pin,
        "bundle_id": result.bundle_id,
        "evidence_fingerprint": result.evidence_fingerprint,
        "canonical_contract_id": None,
        "read_only_execution": True,
        **{name: getattr(result, name) for name in (*OBSERVATION_FLAGS, *DENIAL_FLAGS)},
    }
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode()) > MAX_SUMMARY_BYTES:
        raise ValueError("IV_BUNDLE_INSPECTION_SUMMARY_BYTE_LIMIT")
    return raw, 0 if positive else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in PATH_NAMES:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--build-id-pin", required=True)
    parser.add_argument("--archive-fingerprint", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not _pin(args.build_id_pin) or not _pin(args.archive_fingerprint):
        parser.error("Exact lowercase record ID and reviewed archive fingerprint required")
    paths = tuple(getattr(args, name.replace("-", "_")) for name in PATH_NAMES)
    if any(not 0 < len(raw) <= 4096 or any(ord(char) < 32 for char in raw) for raw in paths):
        parser.error("Bounded nonempty database path strings required")
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "plan": {
                        "inspection_version": VERSION,
                        "service_version": SERVICE_VERSION,
                        "paths_as_supplied": dict(zip(PATH_NAMES, paths, strict=True)),
                        "build_id_pin": args.build_id_pin,
                        "expected_archive_fingerprint": args.archive_fingerprint,
                        "inputs_verified": False,
                        "current_source_checked": False,
                        "read_only_execution": True,
                        "publication_requested": False,
                        "decision_eligibility_asserted": False,
                    },
                },
                sort_keys=True,
            )
        )
        return 0
    try:
        with _open_inputs(paths) as handles:
            from nse_quant.data_platform import research_iv_bundle_revalidation as service

            if service.VERSION != SERVICE_VERSION:
                raise ValueError("IV_BUNDLE_INSPECTION_SERVICE_VERSION_UNSUPPORTED")
            result = service.revalidate_research_iv_bundle(
                *handles,
                build_id_pin=args.build_id_pin,
                expected_archive_fingerprint=args.archive_fingerprint,
            )
            if type(result) is not service.ResearchIvBundleRevalidation:
                raise ValueError("IV_BUNDLE_INSPECTION_TYPED_SERVICE_RESULT_REQUIRED")
            raw, exit_code = _summary(result, args.build_id_pin, args.archive_fingerprint)
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "IV_BUNDLE_INSPECTION_FAILED"}))
        return 1
    print(raw)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
