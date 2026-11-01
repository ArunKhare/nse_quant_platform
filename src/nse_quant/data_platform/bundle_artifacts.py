"""Bounded no-replace bundle artifact I/O. File visibility is not publication."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from nse_quant.data_platform.feature_bundle import (
    MAX_BUNDLE_BYTES,
    decode_quote_bundle,
    valid_pin,
)


class BundleArtifacts:
    """Trusted root; no overwrite, repair, adoption, truncation or rename fallback."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def path(self, bundle_id: str) -> Path:
        if not valid_pin(bundle_id):
            raise ValueError("EXACT_BUNDLE_PIN_REQUIRED")
        return self.root / (bundle_id + ".json")

    def exists(self, bundle_id: str) -> bool:
        target = self.path(bundle_id)
        return target.exists() or target.is_symlink()

    def read_exact(self, bundle_id: str) -> bytes:
        target = self.path(bundle_id)
        if target.is_symlink():
            raise ValueError("BUNDLE_SYMLINK_REQUIRES_REVIEW")
        with target.open("rb") as handle:
            raw = handle.read(MAX_BUNDLE_BYTES + 1)
        decode_quote_bundle(raw, expected_bundle_id=bundle_id)
        return raw

    def write_new(self, raw: bytes, *, bundle_id: str) -> None:
        """Fsync exact file, then hard-link into place; no directory-fsync guarantee.

        An existing destination is NEVER overwritten or silently adopted, even
        if bytes match. Successful linking followed by another error may leave an
        orphan final artifact: retain it for review, never unlink it here.
        """
        decode_quote_bundle(raw, expected_bundle_id=bundle_id)
        target = self.path(bundle_id)
        self.root.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".pending-bundle-", dir=self.root)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
