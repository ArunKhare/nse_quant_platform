"""Bounded read-only capture inspection. Recovery plans never mutate source evidence."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path


@dataclass(frozen=True)
class InspectionLimits:
    max_segments: int = 4096
    max_segment_bytes: int = 8_388_608
    max_total_bytes: int = 1_073_741_824
    max_line_bytes: int = 2_097_152

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in asdict(self).values()):
            raise ValueError("Inspection limits must be positive integers")


@dataclass(frozen=True)
class SegmentHealth:
    filename: str
    size_bytes: int
    sha256: str | None
    complete_records: int
    valid_prefix_bytes: int
    first_invalid_offset: int | None
    sealed: bool
    issues: tuple[str, ...]


@dataclass(frozen=True)
class CaptureHealth:
    report_version: int
    observed_at: str
    session_id: str | None
    source_directory: str
    status: str
    audit_state: str
    audit_job_id: str | None
    automatic_ingestion_allowed: bool
    source_fingerprint: str
    segments: tuple[SegmentHealth, ...]
    issues: tuple[str, ...]

    def recovery_plan(self) -> dict[str, object]:
        candidates = [
            {
                "filename": item.filename,
                "source_sha256": item.sha256,
                "prefix_bytes": item.valid_prefix_bytes,
                "records": item.complete_records,
                "action": "REVIEW_PREFIX_AS_NEW_EVIDENCE_ONLY",
                "auto_ingest": False,
            }
            for item in self.segments
            if (
                self.status != "UNSTABLE_OBSERVATION"
                and not item.sealed
                and item.valid_prefix_bytes > 0
                and item.sha256 is not None
            )
        ]
        return {
            "plan_version": 1,
            "source_fingerprint": self.source_fingerprint,
            "status": self.status,
            "source_mutation_allowed": False,
            "automatic_repair_allowed": False,
            "existing_clean_drain_allowed": self.automatic_ingestion_allowed,
            "review_candidates": candidates,
            "instructions": [
                "Do not truncate, rewrite, delete, reseal or mark the source successful.",
                "Reinspect before any separate approved recovery operation.",
                "Prefix validity does not prove session completeness or market-data quality.",
            ],
        }


def _hash(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def _metadata(path: Path) -> tuple[dict[str, object] | None, str | None, str | None]:
    if path.is_symlink():
        return None, None, "UNSAFE_OR_OVERSIZE"
    if not path.exists():
        return None, None, "MISSING"
    if not path.is_file() or path.stat().st_size > 1_048_576:
        return None, None, "UNSAFE_OR_OVERSIZE"
    try:
        with path.open("rb") as handle:
            raw = handle.read(1_048_577)
    except OSError:
        return None, None, "UNREADABLE"
    if len(raw) > 1_048_576:
        return None, None, "UNSAFE_OR_OVERSIZE"
    try:
        value = json.loads(raw)
    except ValueError:
        return None, hashlib.sha256(raw).hexdigest(), "INVALID_JSON"
    if not isinstance(value, dict):
        return None, hashlib.sha256(raw).hexdigest(), "INVALID_TYPE"
    return value, hashlib.sha256(raw).hexdigest(), None


def _audit(source: Path, wanted_job: str | None) -> tuple[str, str | None]:
    path = source / "audit.duckdb"
    if not path.is_file() or path.is_symlink():
        return "MISSING_OR_UNSAFE", None
    import duckdb

    try:
        conn = duckdb.connect(str(path), read_only=True)
        try:
            query = (
                "SELECT j.job_id, e.state FROM medallion_audit.jobs j "
                "JOIN medallion_audit.job_events e ON j.job_id=e.job_id "
                "WHERE j.command_name='capture.kite_raw@1'"
            )
            params = []
            if wanted_job is not None:
                query += " AND j.job_id=?"
                params.append(wanted_job)
            query += " ORDER BY j.created_at DESC, e.event_index DESC LIMIT 1"
            row = conn.execute(query, params).fetchone()
            return (str(row[1]), str(row[0])) if row is not None else ("NOT_FOUND", None)
        finally:
            conn.close()
    except Exception:
        return "BUSY_OR_UNREADABLE", None


def _valid_envelope(raw: bytes, session_id: str | None, expected_record: int) -> None:
    value = json.loads(raw)
    if not isinstance(value, dict) or type(value.get("envelope_version")) is not int:
        raise ValueError("Envelope type/version")
    if (
        value["envelope_version"] != 1
        or value.get("source") != "kite_websocket"
        or value.get("origin_kind") != "live_provider"
    ):
        raise ValueError("Envelope contract")
    if session_id is not None and value.get("capture_session_id") != session_id:
        raise ValueError("Session identity")
    if value.get("source_record_id") != f"frame-{expected_record:012d}":
        raise ValueError("Receipt sequence")
    received = datetime.fromisoformat(value["received_at"])
    if received.tzinfo is None or received.utcoffset() is None:
        raise ValueError("Naive receipt time")
    if value.get("payload_format") not in {
        "kite_ws_binary_payload",
        "kite_ws_text_bytes",
        "kite_ws_text_reencoded_utf8",
    }:
        raise ValueError("Unknown payload representation")
    payload = base64.b64decode(value["payload_base64"], validate=True)
    if len(payload) > 1_048_576:
        raise ValueError("Payload limit")


def inspect_capture(
    source: Path,
    *,
    limits: InspectionLimits | None = None,
) -> CaptureHealth:
    limits = limits if limits is not None else InspectionLimits()
    if not source.is_dir() or source.is_symlink():
        raise ValueError("Use an existing real capture-session directory")
    issues: list[str] = []
    fingerprints: dict[str, object] = {}
    signatures = {}
    paths = []
    entries = list(islice(source.iterdir(), limits.max_segments * 3 + 257))
    if len(entries) > limits.max_segments * 3 + 256:
        issues.append("DIRECTORY_ENTRY_LIMIT")
    for path in sorted(entries):
        if path.name.startswith("segment-") and path.name.endswith(".jsonl"):
            paths.append(path)
            if len(paths) > limits.max_segments:
                issues.append("SEGMENT_COUNT_LIMIT")
                paths = paths[: limits.max_segments]
                break
    start, start_hash, start_error = _metadata(source / "session_start.json")
    final, final_hash, final_error = _metadata(source / "session_final.json")
    fingerprints["session_start"] = start_hash
    fingerprints["session_final"] = final_hash
    if start_error:
        issues.append("START_" + start_error)
    if final_error:
        issues.append("FINAL_" + final_error)
    session = start.get("capture_session_id") if start else None
    session_id = session if isinstance(session, str) and session.strip() else None
    if session_id is None:
        issues.append("SESSION_ID_UNAVAILABLE")
    if start and start.get("source") != "kite_websocket":
        issues.append("UNEXPECTED_CAPTURE_SOURCE")
    if start and (
        type(start.get("journal_version")) is not int or start.get("journal_version") != 1
    ):
        issues.append("UNSUPPORTED_START_VERSION")
    wanted = final.get("audit_job_id") if final else None
    wanted_job = wanted if isinstance(wanted, str) and wanted else None
    audit_state, audit_job = _audit(source, wanted_job)
    if audit_state != "SUCCEEDED":
        issues.append("AUDIT_NOT_SUCCEEDED")
    if final:
        if (
            final.get("capture_session_id") != session_id
            or type(final.get("journal_version")) is not int
            or final.get("journal_version") != 1
        ):
            issues.append("FINAL_IDENTITY_OR_VERSION")
        if wanted_job is None:
            issues.append("FINAL_AUDIT_ID_UNAVAILABLE")
    results = []
    total_bytes = 0
    expected_record = 1
    for number, path in enumerate(paths, 1):
        segment_issues: list[str] = []
        sealed = (source / (path.name + ".seal.json")).exists()
        if (
            re.fullmatch(r"segment-[0-9]{6}\.jsonl", path.name) is None
            or path.name != f"segment-{number:06d}.jsonl"
        ):
            segment_issues.append("SEGMENT_NAME_OR_ORDER")
        if path.is_symlink() or not path.is_file():
            results.append(SegmentHealth(path.name, 0, None, 0, 0, 0, sealed, ("UNSAFE_SEGMENT",)))
            continue
        info = path.stat()
        signatures[path.name] = (info.st_size, info.st_mtime_ns)
        size = info.st_size
        total_bytes += size
        if size > limits.max_segment_bytes or total_bytes > limits.max_total_bytes:
            issues.append("INSPECTION_BYTE_LIMIT")
            results.append(
                SegmentHealth(path.name, size, None, 0, 0, 0, sealed, ("RESOURCE_LIMIT",))
            )
            continue
        try:
            checksum = _hash(path)
        except OSError:
            results.append(
                SegmentHealth(path.name, size, None, 0, 0, 0, sealed, ("SEGMENT_UNREADABLE",))
            )
            continue
        fingerprints[path.name] = checksum
        prefix = records = 0
        invalid: int | None = None
        with path.open("rb") as handle:
            while True:
                line = handle.readline(limits.max_line_bytes + 1)
                if not line:
                    break
                if len(line) > limits.max_line_bytes:
                    invalid = prefix
                    segment_issues.append("LINE_SIZE_LIMIT")
                    break
                if not line.endswith(b"\n"):
                    invalid = prefix
                    segment_issues.append("TRUNCATED_OR_UNTERMINATED_TAIL")
                    break
                try:
                    _valid_envelope(line, session_id, expected_record)
                except (ValueError, TypeError, KeyError):
                    invalid = prefix
                    segment_issues.append("INVALID_ENVELOPE_OR_SEQUENCE")
                    break
                records += 1
                expected_record += 1
                prefix += len(line)
        if records > 1000:
            segment_issues.append("SEGMENT_RECORD_LIMIT")
        seal, seal_hash, seal_error = _metadata(source / (path.name + ".seal.json"))
        fingerprints[path.name + ".seal.json"] = seal_hash
        if seal_error:
            segment_issues.append("SEAL_" + seal_error)
        elif seal and (
            type(seal.get("journal_version")) is not int
            or seal.get("journal_version") != 1
            or seal.get("file") != path.name
            or seal.get("sha256") != checksum
            or seal.get("bytes") != size
            or seal.get("records") != records
            or seal.get("capture_session_id") != session_id
        ):
            segment_issues.append("SEAL_CONTENT_MISMATCH")
        results.append(
            SegmentHealth(
                path.name, size, checksum, records, prefix, invalid, sealed, tuple(segment_issues)
            )
        )
    known_seals = {item.filename + ".seal.json" for item in results}
    observed_seals = {path.name for path in entries if path.name.endswith(".jsonl.seal.json")}
    if observed_seals - known_seals:
        issues.append("ORPHAN_SEAL")
    actual_seals = [item.filename + ".seal.json" for item in results if item.sealed]
    if final and final.get("seals") != actual_seals:
        issues.append("FINAL_SEAL_LIST_MISMATCH")
    if final and (
        type(final.get("records")) is not int
        or final.get("records") != sum(item.complete_records for item in results)
    ):
        issues.append("FINAL_RECORD_COUNT_MISMATCH")
    changed = False
    for name, signature in signatures.items():
        try:
            info = (source / name).stat()
            changed |= signature != (info.st_size, info.st_mtime_ns)
        except OSError:
            changed = True
    if _metadata(source / "session_start.json")[1] != start_hash:
        changed = True
    if _metadata(source / "session_final.json")[1] != final_hash:
        changed = True
    if changed:
        issues.append("SOURCE_CHANGED_DURING_INSPECTION")
    has_segment_issues = any(item.issues for item in results)
    closed = final is not None and final.get("status") == "CLOSED"
    eligible = closed and not issues and not has_segment_issues
    if changed:
        status = "UNSTABLE_OBSERVATION"
    elif eligible:
        status = "CLOSED_VERIFIED" if expected_record > 1 else "EMPTY_CLOSED_VERIFIED"
    elif final and final.get("status") == "FAILED":
        status = "FAILED_WITH_EVIDENCE"
    elif closed:
        status = "CLOSED_REQUIRES_REVIEW"
    else:
        status = "INCOMPLETE_REQUIRES_REVIEW"
    fingerprints["inspection_limits"] = asdict(limits)
    fingerprints["issues"] = issues
    fingerprints["segment_diagnostics"] = [asdict(item) for item in results]
    fingerprints["audit_state"] = audit_state
    fingerprints["audit_job_id"] = audit_job
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprints,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return CaptureHealth(
        1,
        datetime.now(UTC).isoformat(),
        session_id,
        str(source.resolve()),
        status,
        audit_state,
        audit_job,
        eligible and expected_record > 1,
        fingerprint,
        tuple(results),
        tuple(issues),
    )
