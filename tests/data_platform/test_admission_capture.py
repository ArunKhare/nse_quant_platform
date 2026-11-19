"""Actual receipt DB/audit transactions; publication reader boundary substituted."""

import builtins
import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from nse_quant.data_platform import admission_capture as capture
from nse_quant.data_platform import feature_bundle as codec
from nse_quant.data_platform import publication_admission as policy
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.gold_quote_features import ExactPriceFeature, GoldQuoteCandidate
from nse_quant.data_platform.quote_publication_reader import ResearchPublicationEvidence

T = datetime(2026, 1, 1, tzinfo=UTC)


def evidence():
    value = GoldQuoteCandidate(
        "",
        codec.FEATURE_VERSION,
        "a" * 64,
        "b" * 64,
        "candidate",
        "EXACT_PROVIDER_PRICE_FIELDS",
        source_evidence_fingerprint="c" * 64,
        source_association_fingerprint="d" * 64,
        source_frame_revision_id="e" * 64,
        source_packet_ordinal=0,
        reference_assessment_revision_id="f" * 64,
        reference_row_ordinal=0,
        reference_source_fields_hash="a" * 64,
        provider_token=257,
        price_divisor=100,
        features=(ExactPriceFeature("last_price", 12345, 100, "123.45"),),
        quality_flags=("EXCHANGE_EVENT_TIME_UNKNOWN",),
    )
    value = replace(value, build_id=codec.digest(codec.canonical(asdict(value)).encode()))
    raw = codec.canonical(asdict(value))
    bundle = codec.make_quote_bundle(
        (
            codec.QuoteBundleMember(
                value.build_id,
                codec.GOLD_READER_VERSION,
                "a" * 64,
                ("gold-job",),
                codec.digest(raw.encode()),
                raw,
            ),
        )
    )
    identity = codec.digest(
        codec.canonical(
            [
                ["research-quote-publication@1", "research-only-publication-policy@1"],
                bundle.bundle_id,
                "RESEARCH_ONLY",
            ]
        ).encode()
    )
    return ResearchPublicationEvidence(
        "research-quote-publication-consumer@1",
        identity,
        "verified_research_snapshot",
        "ARCHIVED_CONTENT_AND_PUBLICATION_AUDITS_VERIFIED",
        "RESEARCH_ONLY",
        bundle.bundle_id,
        T.isoformat(),
        T.isoformat(),
        "PLATFORM_RECORD_CLOCK_NOT_PROVIDER_OR_ECONOMIC_VALIDITY",
        ("pub-job",),
        bundle,
        "e" * 64,
        True,
    )


@pytest.fixture
def setup(tmp_path, monkeypatch):
    path = tmp_path / "publications.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute("CREATE TABLE marker (id INTEGER)")
    connection.close()
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "receipts.duckdb"))
    state = {"source": evidence(), "calls": 0}

    def read(conn, *, publication_id):
        assert conn is source
        assert publication_id == state["source"].publication_id
        with pytest.raises(duckdb.InvalidInputException):
            conn.execute("INSERT INTO marker VALUES (1)")
        state["calls"] += 1
        return state["source"]

    monkeypatch.setattr(policy, "read_research_publication", read)

    def run(request=None, **changes):
        args = {
            "publication_id": state["source"].publication_id,
            "request": (
                policy.AdmissionRequest(policy.ARCHIVED_RESEARCH) if request is None else request
            ),
            "actor_id": "test",
            "code_revision": "9ef2f23",
            "initialize": True,
        }
        args.update(changes)
        return capture.capture_publication_admission(source, target, **args)

    yield source, target, state, run
    source.close()
    target.close()


def count(target, table):
    return target.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_full_frozen_receipt_policy_definition_and_audited_attempt(setup):
    _, target, state, run = setup
    result = run()
    assert result["status"] == "ACCEPTED_RESEARCH_ONLY"
    assert result["research_analysis_permitted"] is True
    assert result["decision_eligibility_asserted"] is False
    row = target.execute(
        "SELECT receipt_id,receipt_bytes,input_sha256 FROM decision_inputs.admission_receipts"
    ).fetchone()
    stored = policy.replay_admission_receipt(bytes(row[1]), expected_receipt_id=row[0])
    assert stored.input_sha256 == row[2]
    assert json.loads(stored.frozen_input_json)["source"]["publication_id"] == (
        state["source"].publication_id
    )
    assert count(target, "decision_inputs.admission_contracts") == 1
    assert count(target, "decision_inputs.admission_definitions") == 1
    assert count(target, "decision_inputs.admission_attempts") == 1
    assert target.execute(
        "SELECT state FROM medallion_audit.job_events ORDER BY event_index"
    ).fetchall() == [
        ("PLANNED",),
        ("RUNNING",),
        ("SUCCEEDED",),
    ]


def test_rejected_decision_is_committed_without_permission(setup):
    _, target, _, run = setup
    result = run(policy.AdmissionRequest(policy.POINT_IN_TIME, T, T))
    assert result["status"] == "REJECTED"
    assert result["decision_eligibility_asserted"] is False
    row = target.execute(
        "SELECT reason_codes_json,request_knowledge_cutoff,request_economic_at "
        "FROM decision_inputs.admission_receipts"
    ).fetchone()
    assert "AVAILABILITY_EVIDENCE_UNKNOWN" in json.loads(row[0])
    assert row[1].astimezone(UTC) == T
    assert row[2].astimezone(UTC) == T


def test_exact_retry_reassesses_but_deduplicates_content(setup):
    _, target, state, run = setup
    first, second = run(), run(initialize=False)
    assert first["receipt_id"] == second["receipt_id"]
    assert first["job_id"] != second["job_id"]
    assert second["inserted"] is False
    assert state["calls"] == 2
    assert count(target, "decision_inputs.admission_receipts") == 1
    assert count(target, "decision_inputs.admission_attempts") == 2


def test_changed_source_rejection_preserves_and_links_old_receipt(setup):
    _, target, state, run = setup
    first = run()
    state["source"] = replace(
        state["source"], status="blocked", research_publication_verified=False, bundle=None
    )
    second = run()
    assert first["request_revision_id"] == second["request_revision_id"]
    assert first["receipt_id"] != second["receipt_id"]
    assert second["status"] == "REJECTED"
    row = target.execute(
        "SELECT supersedes_json FROM decision_inputs.admission_receipts WHERE receipt_id=?",
        [second["receipt_id"]],
    ).fetchone()
    assert json.loads(row[0]) == [first["receipt_id"]]
    assert count(target, "decision_inputs.admission_receipts") == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"publication_id": "BAD"},
        {"actor_id": ""},
        {"code_revision": " "},
    ],
)
def test_invalid_request_before_initialization(setup, changes):
    _, target, state, run = setup
    with pytest.raises(ValueError):
        run(**changes)
    assert count(target, "information_schema.tables") == 0
    assert state["calls"] == 0


def test_output_cannot_be_source_or_legacy(setup):
    source, target, state, run = setup
    with pytest.raises(ValueError, match="SEPARATE_ADMISSION_RECEIPT_DATABASE_REQUIRED"):
        capture.capture_publication_admission(
            source,
            source,
            publication_id=state["source"].publication_id,
            request=policy.AdmissionRequest(policy.ARCHIVED_RESEARCH),
            actor_id="test",
            code_revision="head",
            initialize=True,
        )
    target.execute("CREATE TABLE option_stream (id INTEGER)")
    with pytest.raises(ValueError, match="DEDICATED_ADMISSION_RECEIPT_DATABASE_REQUIRED"):
        run()
    assert state["calls"] == 0


def test_source_error_is_failed_execution_not_fabricated_rejection(setup, monkeypatch):
    _, target, _, run = setup

    def fail(*args, **kwargs):
        raise RuntimeError("private source error")

    monkeypatch.setattr(policy, "read_research_publication", fail)
    with pytest.raises(RuntimeError):
        run()
    assert count(target, "decision_inputs.admission_receipts") == 0
    assert count(target, "decision_inputs.admission_definitions") == 0
    assert target.execute(
        "SELECT state,reason_code FROM medallion_audit.job_events ORDER BY event_index DESC LIMIT 1"
    ).fetchone() == (
        "FAILED",
        "EXECUTION_ERROR",
    )


@pytest.mark.parametrize(
    "sql,reason",
    [
        (
            "UPDATE decision_inputs.admission_receipts SET status='ACCEPTED_DECISION'",
            "ADMISSION_RECEIPT_VERSION_CONTENT_MISMATCH",
        ),
        (
            "UPDATE decision_inputs.admission_receipts SET receipt_bytes='bad'::BLOB",
            "ADMISSION_RECEIPT_VERSION_CONTENT_MISMATCH",
        ),
        (
            "UPDATE decision_inputs.admission_receipts SET decision_eligibility_asserted=True",
            "ADMISSION_RECEIPT_VERSION_CONTENT_MISMATCH",
        ),
        (
            "UPDATE decision_inputs.admission_definitions SET definition_json='[]'",
            "ADMISSION_POLICY_VERSION_CONTENT_MISMATCH",
        ),
        (
            "UPDATE decision_inputs.admission_contracts SET contract_json='[]'",
            "ADMISSION_STORE_CONTRACT_VERSION_MISMATCH",
        ),
    ],
)
def test_existing_evidence_never_overwritten(setup, sql, reason):
    _, target, _, run = setup
    run()
    target.execute(sql)
    with pytest.raises(ValueError, match=reason):
        run()
    assert count(target, "decision_inputs.admission_attempts") == 1


def test_domain_link_failure_rolls_back_new_receipt(setup):
    _, target, state, run = setup
    first = run()
    target.execute(
        "ALTER TABLE decision_inputs.admission_attempts ADD COLUMN extra INTEGER DEFAULT 1"
    )
    state["source"] = replace(state["source"], evidence_fingerprint="f" * 64)
    with pytest.raises(duckdb.Error):
        run()
    rows = target.execute("SELECT receipt_id FROM decision_inputs.admission_receipts").fetchall()
    assert rows == [
        (first["receipt_id"],),
    ]
    assert count(target, "decision_inputs.admission_attempts") == 1


def test_final_audit_failure_does_not_repair_old_job(setup, monkeypatch):
    _, target, _, run = setup
    original = AuditLedger.transition

    def transition(self, job, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("audit unavailable")
        return original(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", transition)
    with pytest.raises(RuntimeError):
        run()
    first = target.execute(
        "SELECT first_job_id FROM decision_inputs.admission_receipts"
    ).fetchone()[0]
    monkeypatch.setattr(AuditLedger, "transition", original)
    retry = run()
    assert not retry["inserted"]
    assert target.execute(
        "SELECT state FROM medallion_audit.job_events WHERE job_id=? "
        "ORDER BY event_index DESC LIMIT 1",
        [first],
    ).fetchone() == ("RUNNING",)


def test_request_times_compare_as_instants_across_session_timezone(setup):
    _, target, _, run = setup
    request = policy.AdmissionRequest(policy.POINT_IN_TIME, T, T)
    target.execute("SET TimeZone='Asia/Kolkata'")
    first = run(request)
    second = run(request)
    assert first["receipt_id"] == second["receipt_id"]
    assert not second["inserted"]


def test_schema_and_history_bounds(setup, monkeypatch):
    _, target, state, run = setup
    monkeypatch.setattr(capture, "MAX_HISTORY", 0)
    run()
    state["source"] = replace(state["source"], evidence_fingerprint="f" * 64)
    with pytest.raises(ValueError, match="ADMISSION_RECEIPT_HISTORY_LIMIT"):
        run()
    assert count(target, "decision_inputs.admission_receipts") == 1
    target.execute("UPDATE decision_inputs.admission_schema_versions SET version=2")
    with pytest.raises(ValueError, match="UNSUPPORTED_ADMISSION_STORE_SCHEMA"):
        run()


def test_core_byte_limit_rolls_back_local_contract_and_policy(setup, monkeypatch):
    _, target, _, run = setup
    monkeypatch.setattr(capture, "MAX_RECEIPT_BYTES", 1)
    with pytest.raises(ValueError, match="CAPTURED_ADMISSION_BYTE_LIMIT"):
        run()
    assert count(target, "decision_inputs.admission_contracts") == 0
    assert count(target, "decision_inputs.admission_definitions") == 0
    assert count(target, "decision_inputs.admission_receipts") == 0


def test_catalog_named_decision_inputs_is_unambiguous(setup, tmp_path):
    _, target, _, run = setup
    path = tmp_path / "decision_inputs.duckdb"
    escaped = str(path).replace("'", "''")
    target.execute(f"ATTACH '{escaped}' AS decision_inputs")
    target.execute("USE decision_inputs")
    first = run()
    second = run()
    assert first["receipt_id"] == second["receipt_id"]
    table = capture._name(target, "admission_receipts")
    assert target.execute(f"SELECT count(*) FROM {table}").fetchone() == (1,)


def test_no_initialization_or_in_memory_output_fallback(setup):
    source, target, state, run = setup
    with pytest.raises(duckdb.Error):
        run(initialize=False)
    assert count(target, "information_schema.tables") == 0
    with (
        duckdb.connect(":memory:") as memory,
        pytest.raises(ValueError, match="FILE_BACKED_SOURCE_AND_RECEIPT_DATABASES_REQUIRED"),
    ):
        capture.capture_publication_admission(
            source,
            memory,
            publication_id=state["source"].publication_id,
            request=policy.AdmissionRequest(policy.ARCHIVED_RESEARCH),
            actor_id="test",
            code_revision="head",
            initialize=True,
        )


def cli_arguments(source, target, publication_id):
    return [
        "--publication-db",
        str(source),
        "--receipt-db",
        str(target),
        "--publication-id",
        publication_id,
        "--use-case",
        policy.ARCHIVED_RESEARCH,
    ]


def test_cli_default_plan_never_imports_execution_or_creates_files(tmp_path, monkeypatch, capsys):
    from nse_quant.data_platform.admission_capture_cli import main

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {
            "duckdb",
            "nse_quant.data_platform.admission_capture",
            "nse_quant.data_platform.publication_admission",
        }:
            raise AssertionError("Plan imported execution")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    args = cli_arguments(
        tmp_path / "publications.duckdb", tmp_path / "receipts.duckdb", evidence().publication_id
    )
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PLANNED"
    assert list(tmp_path.iterdir()) == []


def test_cli_real_capture_readonly_source_and_domain_rejection(setup, monkeypatch, capsys):
    from nse_quant.data_platform.admission_capture_cli import main

    source, target, state, _ = setup
    source_path = source.execute("PRAGMA database_list").fetchone()[2]
    target_path = target.execute("PRAGMA database_list").fetchone()[2]
    before = hashlib.sha256(Path(source_path).read_bytes()).hexdigest()

    def read(conn, **kwargs):
        with pytest.raises(duckdb.InvalidInputException):
            conn.execute("INSERT INTO marker VALUES (1)")
        return state["source"]

    monkeypatch.setattr(policy, "read_research_publication", read)
    args = cli_arguments(source_path, target_path, state["source"].publication_id)
    args[-1] = policy.POINT_IN_TIME
    args += [
        "--knowledge-cutoff",
        T.isoformat(),
        "--economic-at",
        T.isoformat(),
        "--execute",
        "--initialize",
        "--code-revision",
        "head",
    ]
    assert main(args) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["execution_status"] == "COMMITTED"
    assert result["status"] == "REJECTED"
    assert result["decision_eligibility_asserted"] is False
    assert "frozen_input_json" not in output
    assert hashlib.sha256(Path(source_path).read_bytes()).hexdigest() == before


def test_cli_requires_explicit_new_target_initialization(tmp_path):
    from nse_quant.data_platform.admission_capture_cli import main

    source = tmp_path / "publications.duckdb"
    connection = duckdb.connect(str(source))
    connection.close()
    target = tmp_path / "new-receipts.duckdb"
    args = cli_arguments(source, target, evidence().publication_id)
    with pytest.raises(SystemExit):
        main(args + ["--execute", "--code-revision", "head"])
    assert not target.exists()


def test_cli_source_exception_redacted_and_connections_closed(setup, monkeypatch, capsys):
    from nse_quant.data_platform.admission_capture_cli import main

    source, target, state, _ = setup
    source_path = source.execute("PRAGMA database_list").fetchone()[2]
    target_path = target.execute("PRAGMA database_list").fetchone()[2]

    def fail(*args, **kwargs):
        raise RuntimeError("SECRET_DETAILS")

    monkeypatch.setattr(policy, "read_research_publication", fail)
    args = cli_arguments(source_path, target_path, state["source"].publication_id)
    assert main(args + ["--execute", "--initialize", "--code-revision", "head"]) == 1
    output = capsys.readouterr().out
    assert "SECRET" not in output
    assert json.loads(output)["reason_code"] == "ADMISSION_CAPTURE_FAILED"


def test_first_attempt_link_failure_rolls_back_receipt_definition_contract(setup, monkeypatch):
    _, target, _, run = setup
    original = capture.assess_publication_use

    def assess(*args, **kwargs):
        result = original(*args, **kwargs)
        target.execute(
            "ALTER TABLE decision_inputs.admission_attempts ADD COLUMN extra INTEGER DEFAULT 1"
        )
        return result

    monkeypatch.setattr(capture, "assess_publication_use", assess)
    with pytest.raises(duckdb.Error):
        run()
    assert count(target, "decision_inputs.admission_receipts") == 0
    assert count(target, "decision_inputs.admission_definitions") == 0
    assert count(target, "decision_inputs.admission_contracts") == 0


def test_old_exact_receipt_retry_does_not_rewrite_history(setup):
    _, target, state, run = setup
    original = state["source"]
    first = run()
    state["source"] = replace(original, evidence_fingerprint="f" * 64)
    second = run()
    state["source"] = original
    retry = run()
    assert retry["receipt_id"] == first["receipt_id"]
    assert retry["inserted"] is False
    newer_links = target.execute(
        "SELECT supersedes_json FROM decision_inputs.admission_receipts WHERE receipt_id=?",
        [second["receipt_id"]],
    ).fetchone()[0]
    assert json.loads(newer_links) == [first["receipt_id"]]
    assert count(target, "decision_inputs.admission_receipts") == 2


def test_policy_version_change_cannot_silently_capture(setup, monkeypatch):
    _, target, _, run = setup
    monkeypatch.setattr(capture, "POLICY_VERSION", "research-publication-admission@2")
    with pytest.raises(ValueError, match="UNSUPPORTED_ADMISSION_CAPTURE_POLICY"):
        run()
    assert count(target, "information_schema.tables") == 0


def test_native_schema_cannot_be_shared_with_other_business_tables(setup):
    _, target, _, run = setup
    target.execute("CREATE SCHEMA decision_inputs")
    target.execute("CREATE TABLE decision_inputs.legacy_workspace (id INTEGER)")
    with pytest.raises(ValueError, match="DEDICATED_ADMISSION_RECEIPT_DATABASE_REQUIRED"):
        run()
    assert count(target, "information_schema.tables") == 1
