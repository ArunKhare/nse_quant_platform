"""Content-addressed manifest files with no-replace, same-directory publication.

Requires filesystem hard-link support. There is no unsafe overwrite fallback.
This is atomic file visibility, not an end-to-end power-loss durability guarantee.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class ManifestStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, payload: bytes) -> Path:
        name = digest(payload) + ".json"
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / name
        descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=self.root)
        staging = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(staging, target)
            except FileExistsError:
                if target.read_bytes() != payload:
                    raise ValueError(
                        "Existing manifest content conflicts with its address"
                    ) from None
            return target
        finally:
            staging.unlink(missing_ok=True)

    def read(self, identity: str) -> bytes:
        if len(identity) != 64 or any(char not in "0123456789abcdef" for char in identity):
            raise ValueError("Manifest identity must be a SHA-256 hex digest")
        payload = (self.root / (identity + ".json")).read_bytes()
        if digest(payload) != identity:
            raise ValueError("Manifest checksum mismatch")
        return payload
