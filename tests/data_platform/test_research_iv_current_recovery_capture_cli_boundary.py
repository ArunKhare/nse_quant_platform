"""Actual CLI/revalidator/plan/audit/artifacts; existing source substitute unchanged.

Supplied for repository QA; NOT sandbox-executed or full native acquisition E2E.
"""

import hashlib
import json
from pathlib import Path

import duckdb
import pytest
from test_research_iv_recovery_capture_revalidation_boundary import archive_case as archive_case
from test_research_iv_recovery_capture_revalidation_boundary import artifact_case as artifact_case
from test_research_iv_recovery_capture_revalidation_boundary import bundle_case as bundle_case
from test_research_iv_recovery_capture_revalidation_boundary import capture_case as capture_case
from test_research_iv_recovery_capture_revalidation_boundary import (
    current_bundle_case as current_bundle_case,
)
from test_research_iv_recovery_capture_revalidation_boundary import (
    current_capture_case as current_capture_case,
)
from test_research_iv_recovery_capture_revalidation_boundary import (
    current_stage_case as current_stage_case,
)
from test_research_iv_recovery_capture_revalidation_boundary import (
    revalidation_case as revalidation_case,
)
from test_research_iv_recovery_capture_revalidation_boundary import scenario as scenario
from test_research_iv_recovery_capture_revalidation_boundary import setup as setup
from test_research_iv_recovery_capture_revalidation_boundary import stage_case as stage_case
from test_research_iv_recovery_capture_revalidation_boundary import writer as writer

from nse_quant.data_platform import research_iv_current_recovery_capture_cli as cli
from nse_quant.data_platform import research_iv_recovery_capture_revalidation as native


def _file(conn):
    row = conn.execute("SELECT current_database()").fetchone()
    assert row is not None
    matches = [
        item[2]
        for item in conn.execute("PRAGMA database_list").fetchall()
        if item[1] == row[0] and item[2]
    ]
    assert len(matches) == 1
    return Path(matches[0])


def closed_inputs(staging, capture, recorded, root):
    stage_path = _file(staging)
    capture_path = _file(capture)
    assert not stage_path.samefile(capture_path)
    capture.close()
    staging.close()
    args = [
        "--staging-db",
        str(stage_path),
        "--capture-db",
        str(capture_path),
        "--artifact-root",
        str(root),
        "--capture-build-id-pin",
        recorded.build_id,
        "--capture-fingerprint",
        recorded.evidence_fingerprint,
        "--execute",
    ]
    return args, (stage_path, capture_path)


def test_actual_cli_positive_readonly_and_no_database_or_artifact_writes(
    current_capture_case,
    monkeypatch,
    capsys,
):
    _, capture, recorded, root, _, staging = current_capture_case
    args, paths = closed_inputs(staging, capture, recorded, root)
    tracked = (*paths, *root.iterdir())
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked}
    real = duckdb.connect
    opened: list[duckdb.DuckDBPyConnection] = []

    def connect(*args, **kwargs):
        assert kwargs == {"read_only": True}
        value = real(*args, **kwargs)
        opened.append(value)
        return value

    monkeypatch.setattr(duckdb, "connect", connect)
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "matched_current_research_iv_recovery_capture"
    assert all(result[key] is True for key in cli.OBSERVATION_FLAGS)
    assert all(result[key] is False for key in cli.DENIAL_FLAGS)
    assert result["capture_build_id"] == recorded.build_id
    assert result["expected_capture_fingerprint"] == recorded.evidence_fingerprint
    assert len(opened) == 2
    for conn in opened:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked} == before
    assert not any(key in result for key in ("capture_before", "fresh_before", "comparison"))


def test_wrong_review_pin_no_native_reconciliation(current_capture_case, monkeypatch, capsys):
    _, capture, recorded, root, _, staging = current_capture_case
    args, _ = closed_inputs(staging, capture, recorded, root)
    args[args.index("--capture-fingerprint") + 1] = "0" * 64
    from nse_quant.data_platform import research_iv_recovery_plan as plan

    def forbidden(*args, **kwargs):
        raise AssertionError("Wrong reviewed pin reached native plan")

    monkeypatch.setattr(plan, "plan_research_iv_stage_recovery", forbidden)
    assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "review_required"
    assert result["current_reconciliation_checked"] is False
    assert result["plan_evidence_fingerprint"] is None and result["evidence_fingerprint"] is None


def test_changed_inventory_is_review_not_pin_refresh(current_capture_case, capsys):
    _, capture, recorded, root, _, staging = current_capture_case
    raw = b"synthetic unrelated matching artifact"
    path = root / (hashlib.sha256(raw).hexdigest() + ".research-iv.json")
    path.write_bytes(raw)
    args, _ = closed_inputs(staging, capture, recorded, root)
    assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["current_reconciliation_checked"] is True
    assert result["exact_recorded_plan_reproduced"] is False
    assert result["capture_unchanged_observed"] is True
    assert result["evidence_fingerprint"] is None and path.read_bytes() == raw


def test_recorded_review_cannot_be_upgraded(capture_case, current_stage_case, monkeypatch, capsys):
    execute, capture, _, root = capture_case
    raw = b"synthetic recorded unresolved artifact"
    path = root / (hashlib.sha256(raw).hexdigest() + ".research-iv.json")
    path.write_bytes(raw)
    recorded = execute()
    path.unlink()
    args, _ = closed_inputs(current_stage_case[1], capture, recorded, root)
    from nse_quant.data_platform import research_iv_recovery_plan as plan

    def forbidden(*args, **kwargs):
        raise AssertionError("Recorded review reached native plan")

    monkeypatch.setattr(plan, "plan_research_iv_stage_recovery", forbidden)
    assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["reason_codes"] == ["RECORDED_RECOVERY_REVIEW_CANNOT_BE_UPGRADED"]
    assert result["archived_recording_verified"] is True
    assert result["current_reconciliation_checked"] is False


def test_native_exception_sanitized_and_actual_handles_closed(
    current_capture_case,
    monkeypatch,
    capsys,
):
    _, capture, recorded, root, _, staging = current_capture_case
    args, _ = closed_inputs(staging, capture, recorded, root)
    real = native.revalidate_research_iv_recovery_capture
    handles: list[duckdb.DuckDBPyConnection] = []

    def observe(*connections, **kwargs):
        handles.extend(connections)
        value = real(*connections, **kwargs)
        assert value.status == "matched_current_research_iv_recovery_capture"
        raise RuntimeError("PRIVATE_POST_NATIVE_EXCEPTION")

    monkeypatch.setattr(native, "revalidate_research_iv_recovery_capture", observe)
    assert cli.main(args) == 1
    captured = capsys.readouterr()
    assert "PRIVATE_POST_NATIVE_EXCEPTION" not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "status": "FAILED",
        "reason_code": "IV_CURRENT_RECOVERY_CAPTURE_INSPECTION_FAILED",
    }
    for conn in handles:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")
