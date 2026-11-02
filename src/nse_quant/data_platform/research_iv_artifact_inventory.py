"""Read-only bounded artifact recovery inventory; no cleanup or ownership decisions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path

VERSION = "research-iv-artifact-recovery-inventory@1"
MAX_ENTRIES = 256
MAX_ARTIFACT_BYTES = 4194304
MAX_PASS_BYTES = 16777216


class IvArtifactInventoryReviewRequired(ValueError):
    """An incomplete/changed observation is unusable; never accept a retained prefix."""


@dataclass(frozen=True)
class ArtifactInventoryEntry:
    name_sha256: str
    artifact_name: str | None
    kind: str
    size_bytes_metadata: int
    content_sha256: str | None = None
    filename_pin_matches: bool = False


@dataclass(frozen=True)
class ResearchIvArtifactInventory:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    first_pass: tuple[ArtifactInventoryEntry, ...]
    second_pass: tuple[ArtifactInventoryEntry, ...]
    unchanged_observed: bool
    evidence_fingerprint: str
    destructive_actions_authorized: bool = False
    stage_ownership_checked: bool = False
    orphan_status_determined: bool = False
    native_sources_checked: bool = False
    canonical_bundle_schema_checked: bool = False
    publication_asserted: bool = False
    decision_eligibility_asserted: bool = False


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _root_state(root: Path) -> tuple[int, int]:
    if not isinstance(root, Path) or not root.is_absolute() or ".." in root.parts:
        raise ValueError("ABSOLUTE_UNAMBIGUOUS_INVENTORY_ROOT_REQUIRED")
    for parent in (root, *root.parents):
        if parent.is_symlink() or parent.is_junction():
            raise IvArtifactInventoryReviewRequired("IV_INVENTORY_REDIRECTED_ROOT")
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise IvArtifactInventoryReviewRequired("IV_INVENTORY_EXISTING_DIRECTORY_REQUIRED")
    return info.st_dev, info.st_ino


def _read(root: Path, name: str, before: os.stat_result) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(root / name, flags)
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise IvArtifactInventoryReviewRequired("IV_INVENTORY_OPENED_FILE_CHANGED")
        raw = handle.read(MAX_ARTIFACT_BYTES + 1)
        after = os.fstat(handle.fileno())
    if (
        len(raw) != before.st_size
        or len(raw) > MAX_ARTIFACT_BYTES
        or (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns)
    ):
        raise IvArtifactInventoryReviewRequired("IV_INVENTORY_READ_FILE_CHANGED")
    return raw


def _pass(root: Path) -> tuple[tuple[ArtifactInventoryEntry, ...], tuple[object, ...]]:
    entries: list[tuple[str, os.stat_result, bool]] = []
    with os.scandir(root) as scan:
        for entry in scan:
            if len(entries) >= MAX_ENTRIES:
                raise IvArtifactInventoryReviewRequired("IV_INVENTORY_ENTRY_LIMIT")
            info = (root / entry.name).lstat()
            redirected = entry.is_symlink() or (root / entry.name).is_junction()
            entries.append((entry.name, info, redirected))
    entries.sort(key=lambda item: item[0])
    observed: list[ArtifactInventoryEntry] = []
    stability: list[object] = []
    total = 0
    for name, info, redirected in entries:
        name_pin = _sha(os.fsencode(name))
        match = re.fullmatch(r"([a-f0-9]{64})\.research-iv\.json", name)
        safe_name = name if match else None
        content: str | None = None
        pin_matches = False
        if redirected:
            kind = "REDIRECT_REVIEW"
        elif not stat.S_ISREG(info.st_mode):
            kind = "NONREGULAR_ENTRY_REVIEW"
        elif match is None:
            kind = (
                "PENDING_REMNANT_REVIEW"
                if name.startswith(".pending-iv-")
                else "FOREIGN_ENTRY_REVIEW"
            )
        elif not 0 < info.st_size <= MAX_ARTIFACT_BYTES:
            kind = "ARTIFACT_SIZE_REVIEW"
        else:
            total += info.st_size
            if total > MAX_PASS_BYTES:
                raise IvArtifactInventoryReviewRequired("IV_INVENTORY_PASS_BYTE_LIMIT")
            content = _sha(_read(root, name, info))
            pin_matches = content == match[1]
            kind = "PINNED_BYTES_UNASSESSED" if pin_matches else "ARTIFACT_PIN_MISMATCH_REVIEW"
        observed.append(
            ArtifactInventoryEntry(
                name_pin,
                safe_name,
                kind,
                info.st_size,
                content,
                pin_matches,
            )
        )
        stability.append(
            (
                name_pin,
                info.st_dev,
                info.st_ino,
                info.st_mode,
                info.st_size,
                info.st_mtime_ns,
                redirected,
            )
        )
    return tuple(observed), tuple(stability)


def inventory_research_iv_artifacts(root: Path) -> ResearchIvArtifactInventory:
    """Two whole passes. Even stable matching bytes NEVER determine stage ownership.

    Read only; regular conforming files only, no recursion, no pending/foreign body
    reads, no native/codec computation, no delete/write/adopt/rename/repair operation.
    Trusted single-owner root required, not a hostile-concurrent-writer boundary.
    """
    identity = _root_state(root)
    first, first_state = _pass(root)
    if _root_state(root) != identity:
        raise IvArtifactInventoryReviewRequired("IV_INVENTORY_ROOT_CHANGED")
    second, second_state = _pass(root)
    if _root_state(root) != identity:
        raise IvArtifactInventoryReviewRequired("IV_INVENTORY_ROOT_CHANGED")
    stable = first == second and first_state == second_state
    status = (
        "observed_artifact_inventory_not_recovery_authorization" if stable else "review_required"
    )
    fingerprint = _sha(
        _canonical(
            [
                VERSION,
                identity,
                [asdict(item) for item in first],
                first_state,
                [asdict(item) for item in second],
                second_state,
                stable,
            ]
        )
    )
    reasons: list[str] = []
    if first != second:
        reasons.append("IV_INVENTORY_ENTRY_OR_CONTENT_CHANGED")
    if first_state != second_state:
        reasons.append("IV_INVENTORY_METADATA_OR_IDENTITY_CHANGED")
    if stable:
        reasons.append("TWO_BOUNDED_OBSERVATIONS_MATCH_NOT_RECOVERY_AUTHORIZATION")
    return ResearchIvArtifactInventory(
        VERSION,
        status,
        tuple(reasons),
        first,
        second,
        stable,
        fingerprint,
    )
