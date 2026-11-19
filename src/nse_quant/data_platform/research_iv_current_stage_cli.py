"""Plan-first bounded current-source inspection of an exact audited research-IV stage."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

VERSION = "research-iv-current-stage-inspection@1"
SERVICE_VERSION = "research-iv-first-stage-current-source-revalidation@1"
PATH_NAMES = (
    "bronze-db",
    "frame-silver-db",
    "reference-silver-db",
    "assessment-db",
    "source-gold-db",
    "archive-db",
    "bundle-archive-db",
    "staging-db",
)
OBSERVATION_FLAGS = (
    "archived_stage_recording_verified",
    "current_source_checked",
    "recorded_native_digests_matched",
    "artifact_bytes_matched",
    "stage_unchanged_observed",
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
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


@contextmanager
def _open_inputs(paths: tuple[str, ...], artifact_root: Path) -> Iterator[tuple[Any, ...]]:
    """Execution only: reuse source aliases, never initialize/open a missing DB for write."""
    if type(paths) is not tuple or len(paths) != 8:
        raise ValueError("EIGHT_EXISTING_IV_STAGE_DATABASES_REQUIRED")
    files = tuple(Path(raw) for raw in paths)
    if any(not path.is_file() for path in files):
        raise ValueError("EXISTING_IV_STAGE_DATABASES_REQUIRED")
    for role, reason in (
        (5, "SEPARATE_IV_MEMBER_ARCHIVE_REQUIRED"),
        (6, "SEPARATE_IV_BUNDLE_ARCHIVE_REQUIRED"),
        (7, "SEPARATE_IV_STAGING_DATABASE_REQUIRED"),
    ):
        if any(files[role].samefile(path) for path in files[:role]):
            raise ValueError(reason)
    if not artifact_root.is_absolute() or ".." in artifact_root.parts:
        raise ValueError("ABSOLUTE_EXACT_IV_STAGE_ARTIFACT_ROOT_REQUIRED")
    for path in (artifact_root, *artifact_root.parents):
        if path.is_symlink() or path.is_junction():
            raise ValueError("IV_STAGE_REDIRECTED_ARTIFACT_ROOT")
    if not artifact_root.is_dir():
        raise ValueError("EXISTING_IV_STAGE_ARTIFACT_ROOT_REQUIRED")
    resolved = artifact_root.resolve()
    for path in files:
        selected = path.resolve()
        if resolved == selected or resolved in selected.parents or selected in resolved.parents:
            raise ValueError("IV_STAGE_ARTIFACT_DATABASE_PATH_OVERLAP")
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


def _summary(result: Any, stage_pin: str, reviewed_fingerprint: str) -> tuple[str, int]:
    """Diagnostic projection ONLY, not durable replay, admission or replacement evidence."""
    if (
        result.version != SERVICE_VERSION
        or result.stage_build_id != stage_pin
        or result.expected_stage_fingerprint != reviewed_fingerprint
        or result.status not in ("matched_current_research_iv_stage", "review_required")
        or any(type(getattr(result, key)) is not bool for key in OBSERVATION_FLAGS)
        or any(getattr(result, key) is not False for key in DENIAL_FLAGS)
        or any(
            getattr(result, key) is not None
            for key in (
                "canonical_contract_id",
                "event_ts",
                "published_at",
            )
        )
        or type(result.reason_codes) is not tuple
        or not 1 <= len(result.reason_codes) <= 64
        or any(
            type(code) is not str or re.fullmatch(r"[A-Z0-9_]{1,128}", code) is None
            for code in result.reason_codes
        )
        or len(set(result.reason_codes)) != len(result.reason_codes)
    ):
        raise ValueError("IV_CURRENT_STAGE_INSPECTION_CONTRACT_MISMATCH")
    positive = result.status == "matched_current_research_iv_stage"
    if positive:
        if (
            not all(getattr(result, key) is True for key in OBSERVATION_FLAGS)
            or not _pin(result.bundle_id)
            or not _pin(result.evidence_fingerprint)
        ):
            raise ValueError("IV_CURRENT_STAGE_INSPECTION_INCOMPLETE_POSITIVE")
    elif result.bundle_id is not None or result.evidence_fingerprint is not None:
        raise ValueError("IV_CURRENT_STAGE_REVIEW_CANNOT_EXPOSE_ACCEPTED_IDS")
    value = {
        "inspection_version": VERSION,
        "service_version": result.version,
        "status": result.status,
        "reason_codes": result.reason_codes,
        "stage_build_id": stage_pin,
        "expected_stage_fingerprint": reviewed_fingerprint,
        "bundle_id": result.bundle_id,
        "evidence_fingerprint": result.evidence_fingerprint,
        "canonical_contract_id": None,
        "event_ts": None,
        "published_at": None,
        "read_only_execution": True,
        **{key: getattr(result, key) for key in (*OBSERVATION_FLAGS, *DENIAL_FLAGS)},
    }
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode()) > MAX_SUMMARY_BYTES:
        raise ValueError("IV_CURRENT_STAGE_INSPECTION_DIAGNOSTIC_LIMIT")
    return raw, 0 if positive else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in PATH_NAMES:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--stage-build-id-pin", required=True)
    parser.add_argument("--stage-fingerprint", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not _pin(args.stage_build_id_pin) or not _pin(args.stage_fingerprint):
        parser.error("Exact lowercase stage ID and reviewed stage fingerprint required")
    paths = tuple(getattr(args, name.replace("-", "_")) for name in PATH_NAMES)
    if any(not 0 < len(raw) <= 4096 or any(ord(char) < 32 for char in raw) for raw in paths):
        parser.error("Bounded nonempty database path strings required")
    if not 0 < len(args.artifact_root) <= 2048 or any(ord(c) < 32 for c in args.artifact_root):
        parser.error("Bounded nonempty artifact-root string required")
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "plan": {
                        "inspection_version": VERSION,
                        "service_version": SERVICE_VERSION,
                        "paths_as_supplied": dict(zip(PATH_NAMES, paths, strict=True)),
                        "artifact_root_as_supplied": args.artifact_root,
                        "stage_build_id_pin": args.stage_build_id_pin,
                        "expected_stage_fingerprint": args.stage_fingerprint,
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
        artifact_root = Path(args.artifact_root)
        with _open_inputs(paths, artifact_root) as handles:
            from nse_quant.data_platform import research_iv_stage_revalidation as service

            if service.VERSION != SERVICE_VERSION:
                raise ValueError("IV_CURRENT_STAGE_INSPECTION_SERVICE_VERSION_UNSUPPORTED")
            result = service.revalidate_research_iv_first_stage(
                *handles,
                stage_build_id_pin=args.stage_build_id_pin,
                expected_stage_fingerprint=args.stage_fingerprint,
                artifact_root=artifact_root,
            )
            if type(result) is not service.ResearchIvCurrentStage:
                raise ValueError("IV_CURRENT_STAGE_INSPECTION_TYPED_RESULT_REQUIRED")
            raw, code = _summary(result, args.stage_build_id_pin, args.stage_fingerprint)
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "IV_CURRENT_STAGE_INSPECTION_FAILED"}))
        return 1
    print(raw)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
