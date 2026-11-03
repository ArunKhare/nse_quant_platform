"""Plan-first read-only inspection of current recovery-capture reconciliation, not pricing."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

VERSION = "research-iv-current-recovery-capture-inspection@1"
SERVICE_VERSION = "research-iv-recovery-capture-current-reconciliation@1"
OBSERVATION_FLAGS = (
    "archived_recording_verified",
    "current_reconciliation_checked",
    "exact_recorded_plan_reproduced",
    "capture_unchanged_observed",
)
DENIAL_FLAGS = (
    "current_source_checked",
    "orphan_status_determined",
    "destructive_actions_authorized",
    "adoption_authorized",
    "retry_authorized",
    "recovery_execution_authorized",
    "publication_asserted",
    "decision_eligibility_asserted",
    "availability_evidence_verified",
    "historical_validity_asserted",
    "option_underlying_identity_binding_verified",
    "scenario_terms_authoritative",
    "model_suitability_verified",
    "source_acquisition_authenticity_asserted",
    "atomic_cross_database_snapshot_asserted",
)
NULL_FIELDS = ("canonical_contract_id", "event_ts", "published_at")
MAX_SUMMARY_BYTES = 16384
MAX_ROOT_ENTRIES = 256


def _pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _literal(value: str, limit: int) -> bool:
    return 0 < len(value) <= limit and all(ord(c) >= 32 for c in value)


@contextmanager
def _open_inputs(
    staging_path: str,
    capture_path: str,
    artifact_root: Path,
) -> Iterator[tuple[Any, Any]]:
    """Execution only; bounded metadata checks, no missing-file creation or body reads."""
    files = (Path(staging_path), Path(capture_path))
    if any(not path.is_file() for path in files):
        raise ValueError("EXISTING_CURRENT_RECOVERY_CAPTURE_DATABASES_REQUIRED")
    if files[0].samefile(files[1]):
        raise ValueError("SEPARATE_CURRENT_RECOVERY_CAPTURE_DATABASES_REQUIRED")
    if not artifact_root.is_absolute() or ".." in artifact_root.parts:
        raise ValueError("ABSOLUTE_EXACT_CURRENT_RECOVERY_CAPTURE_ROOT_REQUIRED")
    for path in (artifact_root, *artifact_root.parents):
        if path.is_symlink() or path.is_junction():
            raise ValueError("CURRENT_RECOVERY_CAPTURE_REDIRECTED_ROOT")
    if not artifact_root.is_dir():
        raise ValueError("EXISTING_CURRENT_RECOVERY_CAPTURE_ROOT_REQUIRED")
    resolved = artifact_root.resolve()
    for path in files:
        selected = path.resolve()
        if resolved == selected or resolved in selected.parents or selected in resolved.parents:
            raise ValueError("CURRENT_RECOVERY_CAPTURE_DATABASE_ROOT_OVERLAP")
    import os

    with os.scandir(artifact_root) as entries:
        for index, entry in enumerate(entries):
            if index >= MAX_ROOT_ENTRIES:
                raise ValueError("CURRENT_RECOVERY_CAPTURE_ROOT_ENTRY_LIMIT")
            child = artifact_root / entry.name
            if child.is_symlink() or child.is_junction():
                raise ValueError("CURRENT_RECOVERY_CAPTURE_REDIRECTED_ENTRY")
            if any(child.samefile(path) for path in files):
                raise ValueError("CURRENT_RECOVERY_CAPTURE_DATABASE_ARTIFACT_HARDLINK")
    import duckdb

    with ExitStack() as stack:
        staging = duckdb.connect(str(files[0]), read_only=True)
        stack.callback(staging.close)
        capture = duckdb.connect(str(files[1]), read_only=True)
        stack.callback(capture.close)
        yield staging, capture


def _summary(result: Any, capture_pin: str, fingerprint: str) -> tuple[str, int]:
    """Diagnostic projection, never retained replay or a replacement verification DTO."""
    if (
        not _pin(capture_pin)
        or not _pin(fingerprint)
        or result.version != SERVICE_VERSION
        or result.capture_build_id != capture_pin
        or result.expected_capture_fingerprint != fingerprint
        or result.status not in ("matched_current_research_iv_recovery_capture", "review_required")
        or any(type(getattr(result, key)) is not bool for key in OBSERVATION_FLAGS)
        or any(getattr(result, key) is not False for key in DENIAL_FLAGS)
        or any(getattr(result, key) is not None for key in NULL_FIELDS)
        or type(result.reason_codes) is not tuple
        or not 1 <= len(result.reason_codes) <= 16
        or any(
            type(c) is not str or re.fullmatch(r"[A-Z0-9_]{1,128}", c) is None
            for c in result.reason_codes
        )
        or len(set(result.reason_codes)) != len(result.reason_codes)
    ):
        raise ValueError("CURRENT_RECOVERY_CAPTURE_INSPECTION_CONTRACT_MISMATCH")
    if (
        result.current_reconciliation_checked
        and not result.archived_recording_verified
        or result.exact_recorded_plan_reproduced
        and not result.current_reconciliation_checked
        or result.capture_unchanged_observed
        and not result.archived_recording_verified
    ):
        raise ValueError("CURRENT_RECOVERY_CAPTURE_INSPECTION_INCONSISTENT_FACTS")
    positive = result.status == "matched_current_research_iv_recovery_capture"
    if positive:
        if (
            not all(getattr(result, key) is True for key in OBSERVATION_FLAGS)
            or not _pin(result.plan_evidence_fingerprint)
            or not _pin(result.evidence_fingerprint)
        ):
            raise ValueError("CURRENT_RECOVERY_CAPTURE_INSPECTION_INCOMPLETE_POSITIVE")
    elif result.plan_evidence_fingerprint is not None or result.evidence_fingerprint is not None:
        raise ValueError("CURRENT_RECOVERY_CAPTURE_REVIEW_CANNOT_EXPOSE_ACCEPTED_IDS")
    value = {
        "inspection_version": VERSION,
        "service_version": result.version,
        "status": result.status,
        "reason_codes": result.reason_codes,
        "capture_build_id": capture_pin,
        "expected_capture_fingerprint": fingerprint,
        "plan_evidence_fingerprint": result.plan_evidence_fingerprint,
        "evidence_fingerprint": result.evidence_fingerprint,
        "read_only_execution": True,
        **{key: getattr(result, key) for key in (*OBSERVATION_FLAGS, *DENIAL_FLAGS)},
        **dict.fromkeys(NULL_FIELDS),
    }
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode()) > MAX_SUMMARY_BYTES:
        raise ValueError("CURRENT_RECOVERY_CAPTURE_INSPECTION_SUMMARY_LIMIT")
    return raw, 0 if positive else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging-db", required=True)
    parser.add_argument("--capture-db", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--capture-build-id-pin", required=True)
    parser.add_argument("--capture-fingerprint", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not _pin(args.capture_build_id_pin) or not _pin(args.capture_fingerprint):
        parser.error("Exact lowercase capture ID and reviewed full capture fingerprint required")
    if not all(_literal(raw, 4096) for raw in (args.staging_db, args.capture_db)):
        parser.error("Bounded nonempty database path strings required")
    if not _literal(args.artifact_root, 2048):
        parser.error("Bounded nonempty artifact-root string required")
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "plan": {
                        "inspection_version": VERSION,
                        "service_version": SERVICE_VERSION,
                        "staging_db_as_supplied": args.staging_db,
                        "capture_db_as_supplied": args.capture_db,
                        "artifact_root_as_supplied": args.artifact_root,
                        "capture_build_id_pin": args.capture_build_id_pin,
                        "expected_capture_fingerprint": args.capture_fingerprint,
                        "inputs_verified": False,
                        "current_reconciliation_checked": False,
                        "read_only_execution": True,
                        **dict.fromkeys(DENIAL_FLAGS, False),
                    },
                },
                sort_keys=True,
            )
        )
        return 0
    try:
        root = Path(args.artifact_root)
        with _open_inputs(args.staging_db, args.capture_db, root) as (staging, capture):
            from nse_quant.data_platform import research_iv_recovery_capture_revalidation as service

            if service.VERSION != SERVICE_VERSION:
                raise ValueError("CURRENT_RECOVERY_CAPTURE_INSPECTION_UNSUPPORTED_SERVICE")
            result = service.revalidate_research_iv_recovery_capture(
                staging,
                capture,
                capture_build_id_pin=args.capture_build_id_pin,
                expected_capture_fingerprint=args.capture_fingerprint,
                artifact_root=root,
            )
            if type(result) is not service.ResearchIvCurrentRecoveryCapture:
                raise ValueError("CURRENT_RECOVERY_CAPTURE_INSPECTION_TYPED_RESULT_REQUIRED")
            raw, code = _summary(result, args.capture_build_id_pin, args.capture_fingerprint)
    except Exception:
        print(
            json.dumps(
                {"status": "FAILED", "reason_code": "IV_CURRENT_RECOVERY_CAPTURE_INSPECTION_FAILED"}
            )
        )
        return 1
    print(raw)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
