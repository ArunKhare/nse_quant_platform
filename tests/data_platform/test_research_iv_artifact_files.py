"""Real file-system tests over synthetic pinned bytes, NOT native research-IV proof."""

import hashlib
import os
from dataclasses import fields
from pathlib import Path
from typing import cast

import pytest

from nse_quant.data_platform import research_iv_artifact_files as artifact


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def files(tmp_path):
    value = artifact.ResearchIvArtifactFiles(tmp_path / "artifacts")
    value.initialize()
    return value


def test_real_write_read_no_overwrite_or_adoption(files):
    raw = b"synthetic bytes, not a native IV artifact"
    pin = digest(raw)
    files.write_new(raw, bundle_id=pin)
    assert files.read_exact(pin) == raw
    before = files.path(pin).stat()
    with pytest.raises(FileExistsError):
        files.write_new(raw, bundle_id=pin)
    after = files.path(pin).stat()
    assert (before.st_ino, before.st_mtime_ns, before.st_size) == (
        after.st_ino,
        after.st_mtime_ns,
        after.st_size,
    )
    assert files.read_exact(pin) == raw
    assert len(list(files.root.iterdir())) == 1


def test_explicit_initialize_no_parent_creation_or_existing_root_adoption(tmp_path):
    missing = artifact.ResearchIvArtifactFiles(tmp_path / "missing")
    with pytest.raises(ValueError, match="EXISTING_DEDICATED"):
        missing.write_new(b"x", bundle_id=digest(b"x"))
    assert not missing.root.exists()
    missing.initialize()
    with pytest.raises(FileExistsError):
        missing.initialize()
    nested = artifact.ResearchIvArtifactFiles(tmp_path / "absent" / "nested")
    with pytest.raises(FileNotFoundError):
        nested.initialize()
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize(
    "pin",
    ["", "a" * 63, "A" * 64, "../x", "g" * 64],
    ids=["empty", "length", "uppercase", "traversal", "hex"],
)
def test_pin_rejected_without_io(files, pin):
    with pytest.raises(ValueError, match="EXACT_IV_ARTIFACT"):
        files.path(pin)
    assert not list(files.root.iterdir())


@pytest.mark.parametrize(
    "raw", [b"", bytearray(b"x"), "x", None], ids=["empty", "mutable", "text", "none"]
)
def test_immutable_bounded_write_bytes(files, raw):
    with pytest.raises(ValueError):
        files.write_new(cast(bytes, raw), bundle_id="a" * 64)
    assert not list(files.root.iterdir())


def test_byte_bound_at_limit_and_over(monkeypatch, files):
    monkeypatch.setattr(artifact, "MAX_BYTES", 4)
    files.write_new(b"xxxx", bundle_id=digest(b"xxxx"))
    assert files.read_exact(digest(b"xxxx")) == b"xxxx"
    with pytest.raises(ValueError):
        files.write_new(b"xxxxx", bundle_id=digest(b"xxxxx"))


def test_wrong_content_pin_rejected_before_file_creation(files):
    with pytest.raises(ValueError):
        files.write_new(b"synthetic", bundle_id="a" * 64)
    assert not list(files.root.iterdir())


@pytest.mark.parametrize("other", ["foreign.txt", ".pending-iv-crash"], ids=["foreign", "pending"])
def test_foreign_and_crash_pending_entries_require_review(files, other):
    (files.root / other).write_bytes(b"retain for review")
    with pytest.raises(ValueError, match="ROOT_CONTENT_REQUIRES_REVIEW"):
        files.write_new(b"new", bundle_id=digest(b"new"))
    assert (files.root / other).read_bytes() == b"retain for review"


def test_entry_count_bound_rejects_new_artifact(monkeypatch, files):
    monkeypatch.setattr(artifact, "MAX_FILES", 1)
    files.write_new(b"first", bundle_id=digest(b"first"))
    with pytest.raises(ValueError, match="ROOT_ENTRY_LIMIT"):
        files.write_new(b"second", bundle_id=digest(b"second"))
    assert files.read_exact(digest(b"first")) == b"first"


def test_regular_directory_at_artifact_name_is_not_readable(files):
    files.path("a" * 64).mkdir()
    with pytest.raises(ValueError, match="ROOT_CONTENT"):
        files.read_exact("a" * 64)


def test_root_redirect_detection_does_not_follow_or_repair(files, monkeypatch):
    real = Path.is_symlink

    def redirected(path):
        return path == files.root or real(path)

    monkeypatch.setattr(Path, "is_symlink", redirected)
    with pytest.raises(ValueError, match="REDIRECTED_ROOT"):
        files.write_new(b"x", bundle_id=digest(b"x"))
    assert not list(files.root.iterdir())


def test_relative_or_dotdot_roots_rejected(tmp_path):
    for path in (Path("relative"), tmp_path / ".." / "ambiguous"):
        with pytest.raises(ValueError, match="ABSOLUTE_UNAMBIGUOUS"):
            artifact.ResearchIvArtifactFiles(path)


@pytest.mark.parametrize(
    "change",
    [b"changed", b"", b"x" * 5],
    ids=["changed", "empty", "oversize"],
)
def test_read_detects_mutation_and_size_without_repair(monkeypatch, files, change):
    monkeypatch.setattr(artifact, "MAX_BYTES", 4)
    raw = b"good"
    files.write_new(raw, bundle_id=digest(raw))
    files.path(digest(raw)).write_bytes(change)
    with pytest.raises(ValueError):
        files.read_exact(digest(raw))
    assert files.path(digest(raw)).read_bytes() == change


def test_link_failure_cleans_temp_but_never_creates_final(files, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("SYNTHETIC_LINK_UNSUPPORTED")

    monkeypatch.setattr(os, "link", fail)
    with pytest.raises(OSError, match="SYNTHETIC_LINK_UNSUPPORTED"):
        files.write_new(b"x", bundle_id=digest(b"x"))
    assert not list(files.root.iterdir())


def test_post_link_exception_preserves_orphan_final_and_forbids_retry(files, monkeypatch):
    real = os.link

    def link_then_fail(*args, **kwargs):
        real(*args, **kwargs)
        raise OSError("SYNTHETIC_AFTER_LINK_FAILURE")

    monkeypatch.setattr(os, "link", link_then_fail)
    with pytest.raises(OSError, match="SYNTHETIC_AFTER_LINK_FAILURE"):
        files.write_new(b"x", bundle_id=digest(b"x"))
    assert files.read_exact(digest(b"x")) == b"x"
    assert len(list(files.root.iterdir())) == 1
    monkeypatch.setattr(os, "link", real)
    with pytest.raises(FileExistsError):
        files.write_new(b"x", bundle_id=digest(b"x"))


def test_destination_race_never_replaces_competing_file(files, monkeypatch):
    real = os.link
    pin = digest(b"new")

    def competing(*args, **kwargs):
        files.path(pin).write_bytes(b"competing")
        real(*args, **kwargs)

    monkeypatch.setattr(os, "link", competing)
    with pytest.raises(FileExistsError):
        files.write_new(b"new", bundle_id=pin)
    assert files.path(pin).read_bytes() == b"competing"
    assert len(list(files.root.iterdir())) == 1


def test_native_module_import_and_default_receipt_make_no_stage_or_authority_claim():
    import inspect

    from nse_quant.data_platform import native_research_iv_artifact as native

    signature = inspect.signature(native.materialize_research_iv_artifact)
    assert "requests" not in signature.parameters and "bundle" not in signature.parameters
    assert (
        signature.parameters["expected_revalidation_fingerprint"].default is inspect.Parameter.empty
    )
    for field in fields(native.ResearchIvArtifactMaterialization):
        if field.name.endswith(("_asserted", "_verified", "_recorded")):
            assert field.default is False
    defaults = {
        field.name: field.default for field in fields(native.ResearchIvArtifactMaterialization)
    }
    assert defaults["event_ts"] is None and defaults["published_at"] is None


def test_fsync_failure_never_links_final_and_cleans_temp(files, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("SYNTHETIC_FSYNC_FAILURE")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError, match="SYNTHETIC_FSYNC_FAILURE"):
        files.write_new(b"x", bundle_id=digest(b"x"))
    assert not list(files.root.iterdir())


def test_open_inode_change_is_rejected_not_repaired(files, monkeypatch):
    raw = b"original"
    pin = digest(raw)
    files.write_new(raw, bundle_id=pin)
    replacement = files.root.parent / "replacement-file"
    replacement.write_bytes(raw)
    real = os.open

    def swap_then_open(path, flags, *args, **kwargs):
        os.replace(replacement, path)
        return real(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_then_open)
    with pytest.raises(ValueError, match="OPEN_IDENTITY_CHANGED"):
        files.read_exact(pin)
    assert files.path(pin).read_bytes() == raw
