"""Bounded no-replace research-IV artifact files; pinned bytes are NOT native proof."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path

VERSION = "research-iv-artifact-files@1"
MAX_BYTES = 4194304
MAX_FILES = 256
SUFFIX = ".research-iv.json"


def valid_pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


class ResearchIvArtifactFiles:
    """Trusted single-owner root; no overwrite/adoption/repair/deletion of final files.

    Offline API checks only bounded bytes/hash. Native codec/source checks belong to
    the materialization service. Concurrent hostile path replacement is not supported.
    """

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or ".." in root.parts:
            raise ValueError("ABSOLUTE_UNAMBIGUOUS_IV_ARTIFACT_ROOT_REQUIRED")
        self.root = root

    def path(self, bundle_id: str) -> Path:
        if not valid_pin(bundle_id):
            raise ValueError("EXACT_IV_ARTIFACT_BUNDLE_PIN_REQUIRED")
        return self.root / (bundle_id + SUFFIX)

    def _parents(self) -> None:
        for path in (self.root, *self.root.parents):
            if path.is_symlink() or path.is_junction():
                raise ValueError("IV_ARTIFACT_REDIRECTED_ROOT_REQUIRES_REVIEW")

    def initialize(self) -> None:
        """Create only the explicit new root; never adopt an existing directory."""
        self._parents()
        self.root.mkdir(parents=False, exist_ok=False)

    def _root(self) -> int:
        self._parents()
        if not self.root.is_dir():
            raise ValueError("EXISTING_DEDICATED_IV_ARTIFACT_ROOT_REQUIRED")
        count = 0
        with os.scandir(self.root) as entries:
            for entry in entries:
                count += 1
                if count > MAX_FILES:
                    raise ValueError("IV_ARTIFACT_ROOT_ENTRY_LIMIT")
                if (
                    re.fullmatch(r"[a-f0-9]{64}\.research-iv\.json", entry.name) is None
                    or not entry.is_file(follow_symlinks=False)
                    or entry.is_symlink()
                ):
                    raise ValueError("IV_ARTIFACT_ROOT_CONTENT_REQUIRES_REVIEW")
        return count

    def read_exact(self, bundle_id: str) -> bytes:
        target = self.path(bundle_id)
        self._root()
        before = target.lstat()
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
            raise ValueError("IV_ARTIFACT_REGULAR_BOUNDED_FILE_REQUIRED")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(target, flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
                before.st_dev,
                before.st_ino,
            ):
                raise ValueError("IV_ARTIFACT_OPEN_IDENTITY_CHANGED")
            raw = handle.read(MAX_BYTES + 1)
        if not 0 < len(raw) <= MAX_BYTES or hashlib.sha256(raw).hexdigest() != bundle_id:
            raise ValueError("IV_ARTIFACT_EXACT_BYTES_MISMATCH")
        return raw

    def write_new(self, raw: bytes, *, bundle_id: str) -> None:
        """Fsync temp bytes then hard-link without replace; no rename fallback.

        Final link may exist even if a later operation/cleanup raises. Never remove
        that final link here. Directory fsync/crash durability are NOT guaranteed.
        """
        target = self.path(bundle_id)
        if (
            type(raw) is not bytes
            or not 0 < len(raw) <= MAX_BYTES
            or hashlib.sha256(raw).hexdigest() != bundle_id
        ):
            raise ValueError("IV_ARTIFACT_BOUNDED_PINNED_BYTES_REQUIRED")
        count = self._root()
        if target.exists() or target.is_symlink():
            raise FileExistsError("IV_ARTIFACT_EXISTS_REVIEW_REQUIRED")
        if count >= MAX_FILES:
            raise ValueError("IV_ARTIFACT_ROOT_ENTRY_LIMIT")
        descriptor, name = tempfile.mkstemp(prefix=".pending-iv-", dir=self.root)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                written = handle.write(raw)
                if written != len(raw):
                    raise OSError("IV_ARTIFACT_INCOMPLETE_WRITE")
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
