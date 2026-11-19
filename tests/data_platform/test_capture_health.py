"""Real journal/audit fixtures; inspection never edits or repairs source evidence."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict

import duckdb
import pytest

from nse_quant.data_platform import capture_health as module
from nse_quant.data_platform.capture_health_cli import main


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def line(number=1):
    return (
        json.dumps(
            {
                "envelope_version": 1,
                "source": "kite_websocket",
                "capture_session_id": "session-1",
                "source_record_id": f"frame-{number:012d}",
                "received_at": "2026-10-30T09:15:00+00:00",
                "origin_kind": "live_provider",
                "payload_format": "kite_ws_binary_payload",
                "payload_base64": base64.b64encode(b"private-payload-do-not-print").decode(),
                "exchange_ts": None,
                "provider_event_id": None,
                "instrument_ref": None,
            }
        ).encode()
        + b"\n"
    )


def session(tmp_path, *, audit_state="SUCCEEDED", records=1, status="CLOSED"):
    source = tmp_path / "session"
    source.mkdir()
    write_json(
        source / "session_start.json",
        {
            "journal_version": 1,
            "capture_session_id": "session-1",
            "source": "kite_websocket",
        },
    )
    seals = []
    if records:
        path = source / "segment-000001.jsonl"
        raw = b"".join(line(number) for number in range(1, records + 1))
        path.write_bytes(raw)
        seal = path.name + ".seal.json"
        seals.append(seal)
        write_json(
            source / seal,
            {
                "journal_version": 1,
                "capture_session_id": "session-1",
                "file": path.name,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "records": records,
            },
        )
    write_json(
        source / "session_final.json",
        {
            "journal_version": 1,
            "capture_session_id": "session-1",
            "status": status,
            "records": records,
            "seals": seals,
            "audit_job_id": "capture-job-1",
        },
    )
    if audit_state is not None:
        conn = duckdb.connect(str(source / "audit.duckdb"))
        conn.execute("CREATE SCHEMA medallion_audit")
        conn.execute(
            "CREATE TABLE medallion_audit.jobs "
            "(job_id VARCHAR, command_name VARCHAR, created_at TIMESTAMPTZ)"
        )
        conn.execute(
            "CREATE TABLE medallion_audit.job_events "
            "(job_id VARCHAR, state VARCHAR, event_index INTEGER)"
        )
        conn.execute(
            "INSERT INTO medallion_audit.jobs VALUES "
            "('capture-job-1', 'capture.kite_raw@1', '2026-10-30 09:15:00+00')"
        )
        conn.execute(
            "INSERT INTO medallion_audit.job_events VALUES ('capture-job-1', ?, 3)", [audit_state]
        )
        conn.close()
    return source


def hashes(source):
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source.iterdir()
        if path.is_file()
    }


def test_clean_capture_is_verified_without_source_changes(tmp_path):
    source = session(tmp_path)
    before = hashes(source)
    report = module.inspect_capture(source)
    assert report.status == "CLOSED_VERIFIED" and report.automatic_ingestion_allowed
    assert hashes(source) == before
    serialized = json.dumps(asdict(report))
    assert "private-payload" not in serialized
    assert base64.b64encode(b"private-payload-do-not-print").decode() not in serialized


def test_fingerprint_is_stable_across_inspections(tmp_path):
    source = session(tmp_path)
    assert module.inspect_capture(source).source_fingerprint == (
        module.inspect_capture(source).source_fingerprint
    )


def test_unsealed_complete_prefix_and_truncated_tail_only_propose_review(tmp_path):
    source = session(tmp_path, status="FAILED", audit_state="FAILED")
    (source / "segment-000001.jsonl.seal.json").unlink()
    with (source / "segment-000001.jsonl").open("ab") as handle:
        handle.write(b'{"partial":')
    before = hashes(source)
    report = module.inspect_capture(source)
    assert not report.automatic_ingestion_allowed
    segment = report.segments[0]
    assert segment.complete_records == 1 and segment.valid_prefix_bytes == len(line())
    assert "TRUNCATED_OR_UNTERMINATED_TAIL" in segment.issues
    plan = report.recovery_plan()
    assert plan["automatic_repair_allowed"] is False
    assert len(plan["review_candidates"]) == 1
    assert hashes(source) == before


def test_invalid_middle_record_does_not_skip_to_later_good_data(tmp_path):
    source = session(tmp_path, records=1)
    (source / "segment-000001.jsonl").write_bytes(line() + b"not-json\n" + line(3))
    report = module.inspect_capture(source)
    assert not report.automatic_ingestion_allowed
    assert report.segments[0].complete_records == 1
    assert report.segments[0].first_invalid_offset == len(line())


def test_corrupt_sealed_data_is_not_a_recovery_prefix_candidate(tmp_path):
    source = session(tmp_path)
    (source / "segment-000001.jsonl").write_bytes(line() + b"bad\n")
    report = module.inspect_capture(source)
    assert not report.automatic_ingestion_allowed
    assert report.recovery_plan()["review_candidates"] == []


def test_missing_final_does_not_mean_healthy_active_capture(tmp_path):
    source = session(tmp_path, audit_state="RUNNING")
    (source / "session_final.json").unlink()
    report = module.inspect_capture(source)
    assert report.status == "INCOMPLETE_REQUIRES_REVIEW"
    assert "FINAL_MISSING" in report.issues


@pytest.mark.parametrize("audit_state", [None, "RUNNING", "FAILED", "CANCELLED"])
def test_non_successful_audit_denies_ingestion(tmp_path, audit_state):
    source = session(tmp_path, audit_state=audit_state)
    assert not module.inspect_capture(source).automatic_ingestion_allowed


def test_empty_clean_session_is_not_ingestible_data(tmp_path):
    report = module.inspect_capture(session(tmp_path, records=0))
    assert report.status == "EMPTY_CLOSED_VERIFIED"
    assert not report.automatic_ingestion_allowed


def test_resource_limit_is_explicit(tmp_path):
    source = session(tmp_path)
    report = module.inspect_capture(source, limits=module.InspectionLimits(max_total_bytes=1))
    assert not report.automatic_ingestion_allowed
    assert "INSPECTION_BYTE_LIMIT" in report.issues
    assert report.segments[0].sha256 is None


def test_orphan_seal_is_reported(tmp_path):
    source = session(tmp_path)
    write_json(source / "segment-999999.jsonl.seal.json", {})
    report = module.inspect_capture(source)
    assert "ORPHAN_SEAL" in report.issues and not report.automatic_ingestion_allowed


def test_changed_source_is_unstable_not_clean(tmp_path, monkeypatch):
    source = session(tmp_path)
    original = module._hash

    def changing(path):
        result = original(path)
        with path.open("ab") as handle:
            handle.write(b"changed")
        return result

    monkeypatch.setattr(module, "_hash", changing)
    report = module.inspect_capture(source)
    assert report.status == "UNSTABLE_OBSERVATION" and not report.automatic_ingestion_allowed


def test_busy_audit_is_not_reported_as_corrupt(tmp_path, monkeypatch):
    source = session(tmp_path)

    def busy(*args, **kwargs):
        raise OSError("simulated writer lock")

    monkeypatch.setattr(duckdb, "connect", busy)
    report = module.inspect_capture(source)
    assert report.audit_state == "BUSY_OR_UNREADABLE"
    assert not report.automatic_ingestion_allowed


def test_cli_default_is_read_only_and_require_clean_is_explicit(tmp_path, capsys):
    source = session(tmp_path, status="FAILED")
    before = hashes(source)
    assert main(["--session-dir", str(source)]) == 0
    assert main(["--session-dir", str(source), "--require-clean"]) == 2
    assert "FAILED_WITH_EVIDENCE" in capsys.readouterr().out
    assert hashes(source) == before


def test_publication_inside_source_is_rejected_before_writes(tmp_path):
    source = session(tmp_path)
    before = hashes(source)
    with pytest.raises(SystemExit) as error:
        main(
            [
                "--session-dir",
                str(source),
                "--publish-plan",
                "--output-root",
                str(source),
                "--code-revision",
                "test-commit",
            ]
        )
    assert error.value.code == 2 and hashes(source) == before


def test_missing_directory_does_not_create_it(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(ValueError):
        module.inspect_capture(missing)
    assert not missing.exists()
