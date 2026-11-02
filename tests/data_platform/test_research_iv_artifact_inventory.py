"""Actual bounded filesystem inventory over synthetic bytes; no native computation mocks."""

import builtins
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from nse_quant.data_platform import research_iv_artifact_inventory as inventory
from nse_quant.data_platform.research_iv_inventory_cli import main


def artifact(root, raw):
    name = hashlib.sha256(raw).hexdigest() + ".research-iv.json"
    path = root / name
    path.write_bytes(raw)
    return path


def test_matching_arbitrary_bytes_are_unassessed_not_native_or_stage_proof(tmp_path):
    path = artifact(tmp_path, b"not JSON or native IV evidence")
    before = path.stat()
    value = inventory.inventory_research_iv_artifacts(tmp_path)
    assert value.unchanged_observed
    assert value.first_pass == value.second_pass
    assert value.first_pass[0].kind == "PINNED_BYTES_UNASSESSED"
    assert value.first_pass[0].filename_pin_matches
    assert value.first_pass[0].artifact_name == path.name
    assert value == inventory.inventory_research_iv_artifacts(tmp_path)
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns, before.st_ino) == (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
    )
    for key in (
        "destructive_actions_authorized",
        "stage_ownership_checked",
        "orphan_status_determined",
        "native_sources_checked",
        "canonical_bundle_schema_checked",
        "publication_asserted",
        "decision_eligibility_asserted",
    ):
        assert asdict(value)[key] is False


def test_empty_root_is_only_an_observation(tmp_path):
    value = inventory.inventory_research_iv_artifacts(tmp_path)
    assert value.first_pass == value.second_pass == ()
    assert value.status == "observed_artifact_inventory_not_recovery_authorization"
    assert not value.orphan_status_determined


def test_pending_foreign_directory_names_redacted_no_body_reads(tmp_path, monkeypatch):
    for name in (".pending-iv-SECRET", "SECRET-foreign.txt"):
        (tmp_path / name).write_bytes(b"RAW_SECRET_PAYLOAD")
    (tmp_path / "SECRET-directory").mkdir()

    def forbidden(*args, **kwargs):
        raise AssertionError("Read pending/foreign/nonregular body")

    monkeypatch.setattr(os, "open", forbidden)
    value = inventory.inventory_research_iv_artifacts(tmp_path)
    assert {item.kind for item in value.first_pass} == {
        "PENDING_REMNANT_REVIEW",
        "FOREIGN_ENTRY_REVIEW",
        "NONREGULAR_ENTRY_REVIEW",
    }
    raw = json.dumps(asdict(value))
    assert "SECRET" not in raw
    assert all(
        item.artifact_name is None and item.content_sha256 is None for item in value.first_pass
    )
    assert len(list(tmp_path.iterdir())) == 3


def test_artifact_pin_mismatch_is_reported_not_repaired(tmp_path):
    path = tmp_path / ("a" * 64 + ".research-iv.json")
    path.write_bytes(b"mismatch")
    value = inventory.inventory_research_iv_artifacts(tmp_path)
    assert value.first_pass[0].kind == "ARTIFACT_PIN_MISMATCH_REVIEW"
    assert not value.first_pass[0].filename_pin_matches
    assert path.read_bytes() == b"mismatch"


@pytest.mark.parametrize("raw", [b"", b"x" * 5], ids=["empty", "oversize"])
def test_invalid_size_is_metadata_review_without_body_read(tmp_path, monkeypatch, raw):
    monkeypatch.setattr(inventory, "MAX_ARTIFACT_BYTES", 4)
    artifact(tmp_path, raw)

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid-sized artifact body read")

    monkeypatch.setattr(os, "open", forbidden)
    value = inventory.inventory_research_iv_artifacts(tmp_path)
    assert value.first_pass[0].kind == "ARTIFACT_SIZE_REVIEW"
    assert value.first_pass[0].content_sha256 is None


def test_aggregate_byte_budget_never_accepts_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(inventory, "MAX_PASS_BYTES", 5)
    artifact(tmp_path, b"aaa")
    artifact(tmp_path, b"bbb")
    with pytest.raises(inventory.IvArtifactInventoryReviewRequired, match="PASS_BYTE_LIMIT"):
        inventory.inventory_research_iv_artifacts(tmp_path)
    assert len(list(tmp_path.iterdir())) == 2


def test_entry_budget_counts_foreign_and_pending_not_only_final_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(inventory, "MAX_ENTRIES", 1)
    (tmp_path / "foreign").write_bytes(b"x")
    (tmp_path / ".pending-iv-x").write_bytes(b"x")
    with pytest.raises(inventory.IvArtifactInventoryReviewRequired, match="ENTRY_LIMIT"):
        inventory.inventory_research_iv_artifacts(tmp_path)


@pytest.mark.parametrize("mutation", ["change", "add", "remove"], ids=["change", "add", "remove"])
def test_two_pass_drift_retains_both_observations_and_never_authorizes(
    tmp_path,
    monkeypatch,
    mutation,
):
    path = artifact(tmp_path, b"original")
    real = inventory._pass
    calls = 0

    def observe(root):
        nonlocal calls
        result = real(root)
        calls += 1
        if calls == 1:
            if mutation == "change":
                path.write_bytes(b"changed")
            elif mutation == "add":
                (tmp_path / ".pending-iv-new").write_bytes(b"pending")
            else:
                path.unlink()
        return result

    monkeypatch.setattr(inventory, "_pass", observe)
    value = inventory.inventory_research_iv_artifacts(tmp_path)
    assert calls == 2 and not value.unchanged_observed
    assert value.status == "review_required"
    assert value.first_pass != value.second_pass
    assert not value.destructive_actions_authorized


def test_root_redirect_is_rejected_without_scan(tmp_path, monkeypatch):
    real = Path.is_symlink

    def redirected(path):
        return path == tmp_path or real(path)

    monkeypatch.setattr(Path, "is_symlink", redirected)
    with pytest.raises(inventory.IvArtifactInventoryReviewRequired, match="REDIRECTED_ROOT"):
        inventory.inventory_research_iv_artifacts(tmp_path)


def test_entry_redirect_not_followed_or_deleted(tmp_path, monkeypatch):
    (tmp_path / ".pending-iv-x").write_bytes(b"keep")
    real = Path.is_junction

    def redirected(path):
        return path.name == ".pending-iv-x" or real(path)

    monkeypatch.setattr(Path, "is_junction", redirected)
    value = inventory.inventory_research_iv_artifacts(tmp_path)
    assert value.first_pass[0].kind == "REDIRECT_REVIEW"
    assert (tmp_path / ".pending-iv-x").read_bytes() == b"keep"


def test_root_identity_change_fails_instead_of_reporting_stable(tmp_path, monkeypatch):
    real = inventory._root_state
    calls = 0

    def observe(path):
        nonlocal calls
        dev, inode = real(path)
        calls += 1
        return dev, inode if calls == 1 else inode + 1

    monkeypatch.setattr(inventory, "_root_state", observe)
    with pytest.raises(inventory.IvArtifactInventoryReviewRequired, match="ROOT_CHANGED"):
        inventory.inventory_research_iv_artifacts(tmp_path)


def test_missing_relative_ambiguous_and_file_roots_never_initialized(tmp_path):
    for path in (Path("relative"), tmp_path / ".." / "ambiguous"):
        with pytest.raises(ValueError):
            inventory.inventory_research_iv_artifacts(path)
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        inventory.inventory_research_iv_artifacts(missing)
    assert not missing.exists()
    file_root = tmp_path / "file-root"
    file_root.write_bytes(b"retain")
    with pytest.raises(inventory.IvArtifactInventoryReviewRequired):
        inventory.inventory_research_iv_artifacts(file_root)
    assert file_root.read_bytes() == b"retain"


def test_opened_file_replacement_detected(tmp_path, monkeypatch):
    path = artifact(tmp_path, b"original")
    before = path.stat()
    replacement = tmp_path.parent / (tmp_path.name + "-replacement")
    replacement.write_bytes(b"original")
    os.replace(replacement, path)
    with pytest.raises(inventory.IvArtifactInventoryReviewRequired, match="OPENED_FILE_CHANGED"):
        inventory._read(tmp_path, path.name, before)


def test_no_io_or_execution_import_in_default_plan(monkeypatch, capsys):
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(
            (
                "nse_quant.data_platform.research_iv_artifact_files",
                "nse_quant.data_platform.research_iv_artifact_inventory",
            )
        ):
            raise AssertionError("Plan imported execution implementation")
        return real_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("Plan performed I/O")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", guarded)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(os, "scandir", forbidden)
        for method in ("open", "resolve", "exists", "is_dir", "stat", "lstat", "is_symlink"):
            patch.setattr(Path, method, forbidden)
        assert main(["--artifact-root", "missing/../literal-root"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "PLANNED"
    assert value["artifact_root_as_supplied"] == "missing/../literal-root"
    assert value["filesystem_checked"] is False
    assert value["destructive_actions_authorized"] is False


@pytest.mark.parametrize("raw", ["", "x" * 2049, "bad\nroot"], ids=["empty", "long", "control"])
def test_bad_plan_root_strings_rejected(raw):
    with pytest.raises(SystemExit) as error:
        main(["--artifact-root", raw])
    assert error.value.code == 2


def test_metadata_only_drift_is_explicit_even_if_hashes_match(tmp_path, monkeypatch):
    path = artifact(tmp_path, b"same bytes")
    real = inventory._pass
    calls = 0

    def observe(root):
        nonlocal calls
        result = real(root)
        calls += 1
        if calls == 1:
            info = path.stat()
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000000))
        return result

    monkeypatch.setattr(inventory, "_pass", observe)
    value = inventory.inventory_research_iv_artifacts(tmp_path)
    assert value.first_pass == value.second_pass
    assert value.status == "review_required" and not value.unchanged_observed
    assert value.reason_codes == ("IV_INVENTORY_METADATA_OR_IDENTITY_CHANGED",)
