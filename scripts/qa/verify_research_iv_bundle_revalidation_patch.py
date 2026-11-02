"""Verify this ZIP's exact payload set/checksums; not Git, QA or native-source proof."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from zipfile import ZipFile

PAYLOADS = frozenset(
    {
        "src/nse_quant/data_platform/research_iv_bundle_observation.py",
        "src/nse_quant/data_platform/research_iv_bundle_revalidation.py",
        "tests/data_platform/test_research_iv_bundle_observation.py",
        "tests/data_platform/test_research_iv_bundle_revalidation_boundary.py",
        "scripts/qa/qa_research_iv_bundle_revalidation.ps1",
        "scripts/qa/verify_research_iv_bundle_revalidation_patch.py",
        "docs/RESEARCH_IV_BUNDLE_CURRENT_REVALIDATION.md",
        "docs/RESEARCH_IV_BUNDLE_REVALIDATION_VERIFICATION.md",
    }
)
MANIFEST = "RESEARCH_IV_BUNDLE_REVALIDATION_SHA256SUMS.txt"


def verify(archive: Path, expected_sha256: str) -> None:
    if re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is None:
        raise ValueError("EXACT_ARCHIVE_SHA256_REQUIRED")
    if not 0 < archive.stat().st_size <= 2097152:
        raise ValueError("PATCH_ARCHIVE_SIZE_INVALID")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("PATCH_ARCHIVE_SHA256_MISMATCH")
    with ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len(PAYLOADS) + 1 or set(names) != PAYLOADS | {MANIFEST}:
            raise ValueError("PATCH_ARCHIVE_EXACT_MEMBER_SET_MISMATCH")
        if any(not 0 < item.file_size <= 524288 for item in bundle.infolist()):
            raise ValueError("PATCH_MEMBER_SIZE_INVALID")
        if bundle.testzip() is not None:
            raise ValueError("PATCH_ARCHIVE_CRC_FAILURE")
        raw_manifest = bundle.read(MANIFEST)
        entries: dict[str, str] = {}
        for line in raw_manifest.decode("utf-8").splitlines():
            match = re.fullmatch(r"([a-f0-9]{64})  ([A-Za-z0-9_./-]+)", line)
            if match is None or match[2] in entries:
                raise ValueError("PATCH_MANIFEST_INVALID")
            entries[match[2]] = match[1]
        if set(entries) != PAYLOADS:
            raise ValueError("PATCH_MANIFEST_EXACT_PAYLOAD_SET_MISMATCH")
        for name in PAYLOADS | {MANIFEST}:
            raw = bundle.read(name)
            if name != MANIFEST and hashlib.sha256(raw).hexdigest() != entries[name]:
                raise ValueError("PATCH_PAYLOAD_SHA256_MISMATCH")
            if not raw.endswith(b"\n") or b"\r" in raw:
                raise ValueError("PATCH_PAYLOAD_LINE_ENDINGS_INVALID")
            if any(line.rstrip(b" \t") != line for line in raw.splitlines()):
                raise ValueError("PATCH_PAYLOAD_WHITESPACE_INVALID")
    print(f"Verified archive SHA-256, CRC, {len(names)} exact members, {len(entries)} payloads")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    verify(args.archive, args.sha256)


if __name__ == "__main__":
    main()
