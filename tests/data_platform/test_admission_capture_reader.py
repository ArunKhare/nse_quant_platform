"""Native DuckDB capture/reader integration, with publication-reader boundary replaced.

These are not full source-to-decision end-to-end tests.
"""

from dataclasses import replace
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import admission_capture as capture
from nse_quant.data_platform import admission_capture_reader as reader
from nse_quant.data_platform import publication_admission as policy
from nse_quant.data_platform.quote_publication_reader import ResearchPublicationEvidence


@pytest.fixture
def captured(tmp_path, monkeypatch):
    source_path = tmp_path / "source.duckdb"
    with duckdb.connect(str(source_path)) as source:
        source.execute("CREATE TABLE marker(id INTEGER)")
    source = duckdb.connect(str(source_path), read_only=True)
    target = duckdb.connect(str(tmp_path / "decision_inputs.duckdb"))
    state = {
        "value": ResearchPublicationEvidence(
            "research-quote-publication-consumer@1", "a" * 64, "blocked", "SOURCE_BLOCKED"
        )
    }
    monkeypatch.setattr(policy, "read_research_publication", lambda *a, **k: state["value"])

    def run():
        return capture.capture_publication_admission(
            source,
            target,
            publication_id="a" * 64,
            request=policy.AdmissionRequest(policy.ARCHIVED_RESEARCH),
            actor_id="reader-test",
            code_revision="test",
            initialize=True,
        )

    first = run()
    yield source, target, state, run, first
    source.close()
    target.close()


def test_rejected_capture_is_valid_archived_provenance_not_permission(captured):
    _, target, _, _, first = captured
    result = reader.read_admission_capture(target, receipt_id=first["receipt_id"])
    assert result.archived_integrity_verified
    assert result.native_capture_provenance_verified
    assert result.reassessment_history_verified
    assert result.archived_policy_status == "REJECTED"
    assert result.pinned_receipt_is_history_head
    assert not result.current_request_checked
    assert not result.research_analysis_authorized
    assert not result.decision_eligibility_asserted
    assert not result.replay_authenticity_asserted


def test_full_history_old_retry_never_revives_old_head(captured):
    _, target, state, run, first = captured
    original = state["value"]
    state["value"] = replace(original, reason_code="SOURCE_CHANGED")
    second = run()
    state["value"] = original
    assert run()["receipt_id"] == first["receipt_id"]
    old = reader.read_admission_capture(target, receipt_id=first["receipt_id"])
    assert old.reassessment_history_verified
    assert not old.pinned_receipt_is_history_head
    assert old.history_head_receipt_id == second["receipt_id"]


def test_failed_unlinked_attempt_is_not_filtered_out(captured):
    _, target, _, _, first = captured
    from nse_quant.data_platform.audit import AuditLedger, JobState

    job = AuditLedger(target).plan_job(
        command_name=capture.COMMAND,
        actor_id="test",
        code_revision="test",
        scope_ref="sha256:" + first["request_revision_id"],
        config_hash="untrusted",
    )
    AuditLedger(target).transition(job, JobState.FAILED, "EXECUTION_ERROR")
    result = reader.read_admission_capture(target, receipt_id=first["receipt_id"])
    assert result.native_capture_provenance_verified
    assert not result.reassessment_history_verified
    assert not result.pinned_receipt_is_history_head


def test_incomplete_origin_not_healed_by_successful_retry(captured):
    _, target, _, run, first = captured
    target.execute(
        "DELETE FROM medallion_audit.job_events WHERE job_id=? AND state='SUCCEEDED'",
        [first["job_id"]],
    )
    run()
    result = reader.read_admission_capture(target, receipt_id=first["receipt_id"])
    assert result.archived_integrity_verified
    assert not result.native_capture_provenance_verified
    assert not result.reassessment_history_verified


@pytest.mark.parametrize(
    ("table", "assignment"),
    [
        ("admission_receipts", "status='ACCEPTED_DECISION'"),
        ("admission_receipts", "research_analysis_permitted=True"),
        ("admission_receipts", "receipt_bytes='bad'::BLOB"),
        ("admission_receipts", "supersedes_json='[true]'"),
        ("admission_contracts", "contract_json='[]'"),
        ("admission_definitions", "definition_json='[]'"),
    ],
)
def test_corruption_fails_closed(captured, table, assignment):
    _, target, _, _, first = captured
    qualified_table = reader._name(target, "decision_inputs", table)
    target.execute(f"UPDATE {qualified_table} SET {assignment}")

    result = reader.read_admission_capture(
        target,
        receipt_id=first["receipt_id"],
    )
    assert not result.reassessment_history_verified
    assert not result.decision_eligibility_asserted


def test_timezone_and_read_only_connection(captured):
    _, target, _, _, first = captured
    target.execute("SET TimeZone='Asia/Kolkata'")
    assert reader.read_admission_capture(
        target, receipt_id=first["receipt_id"]
    ).reassessment_history_verified
    path = target.execute("PRAGMA database_list").fetchone()[2]
    target.close()
    with duckdb.connect(path, read_only=True) as connection:
        before = connection.execute("SELECT count(*) FROM medallion_audit.job_events").fetchone()
        assert reader.read_admission_capture(
            connection, receipt_id=first["receipt_id"]
        ).reassessment_history_verified
        assert (
            connection.execute("SELECT count(*) FROM medallion_audit.job_events").fetchone()
            == before
        )


def test_bounds_block_without_salvage(captured, monkeypatch):
    _, target, _, _, first = captured
    monkeypatch.setattr(reader, "MAX_TOTAL_BYTES", 1)
    result = reader.read_admission_capture(target, receipt_id=first["receipt_id"])
    assert result.archived_integrity_verified
    assert result.native_capture_provenance_verified
    assert not result.reassessment_history_verified


def test_missing_schema_operational_error_propagates(tmp_path):
    with duckdb.connect(str(tmp_path / "missing.duckdb")) as conn, pytest.raises(duckdb.Error):
        reader.read_admission_capture(conn, receipt_id="a" * 64)


@pytest.mark.parametrize(
    "graph",
    [
        {"a": ("b",), "b": ("a",)},
        {"a": (), "b": ()},
        {"a": ("missing",)},
        {"a": (), "b": ("a", "a")},
        {"a": (), "b": ("a",), "c": ("b",)},
    ],
)
def test_graph_rejects_cycles_forks_missing_and_incomplete_edges(graph):
    with pytest.raises(ValueError):
        reader._head(graph)


def test_graph_orders_by_links_not_clock_or_hash():
    assert reader._head({"z": (), "a": ("z",), "b": ("a", "z")}) == "b"


def test_lifecycle_requires_exact_success_sequence():
    now = datetime.now(UTC)
    assert reader._lifecycle([(1, "SUCCEEDED", now, None)]) == "INVALID"
    assert reader._lifecycle([(1, "PLANNED", now, None), (2, "RUNNING", now, None)]) == "INCOMPLETE"
    assert (
        reader._lifecycle(
            [(1, "PLANNED", now, None), (2, "RUNNING", now, None), (3, "SUCCEEDED", now, None)]
        )
        == "SUCCEEDED"
    )


def test_cli_plan_no_database_creation(tmp_path, capsys):
    from nse_quant.data_platform.admission_capture_inspect_cli import main

    assert main(["--receipt-db", str(tmp_path / "absent.duckdb"), "--receipt-id", "a" * 64]) == 0
    assert list(tmp_path.iterdir()) == []
    assert '"PLANNED"' in capsys.readouterr().out


def test_accepted_archival_receipt_still_never_authorizes(captured):
    from dataclasses import asdict

    from nse_quant.data_platform import feature_bundle as codec
    from nse_quant.data_platform.gold_quote_features import ExactPriceFeature, GoldQuoteCandidate

    source, target, state, _, _ = captured
    candidate = GoldQuoteCandidate(
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
    candidate_hash = codec.digest(codec.canonical(asdict(candidate)).encode())
    candidate = replace(candidate, build_id=candidate_hash)
    raw = codec.canonical(asdict(candidate))
    bundle = codec.make_quote_bundle(
        (
            codec.QuoteBundleMember(
                candidate.build_id,
                codec.GOLD_READER_VERSION,
                "a" * 64,
                ("gold-job",),
                codec.digest(raw.encode()),
                raw,
            ),
        )
    )
    pin = codec.digest(
        codec.canonical(
            [
                ["research-quote-publication@1", "research-only-publication-policy@1"],
                bundle.bundle_id,
                "RESEARCH_ONLY",
            ]
        ).encode()
    )
    clock = datetime.now(UTC).isoformat()
    state["value"] = ResearchPublicationEvidence(
        "research-quote-publication-consumer@1",
        pin,
        "verified_research_snapshot",
        "ARCHIVED_CONTENT_AND_PUBLICATION_AUDITS_VERIFIED",
        "RESEARCH_ONLY",
        bundle.bundle_id,
        clock,
        clock,
        "PLATFORM_RECORD_CLOCK_NOT_PROVIDER_OR_ECONOMIC_VALIDITY",
        ("pub-job",),
        bundle,
        "e" * 64,
        True,
    )
    first = capture.capture_publication_admission(
        source,
        target,
        publication_id=pin,
        request=policy.AdmissionRequest(policy.ARCHIVED_RESEARCH),
        actor_id="test",
        code_revision="test",
        initialize=False,
    )
    result = reader.read_admission_capture(target, receipt_id=first["receipt_id"])
    assert result.archived_policy_status == "ACCEPTED_RESEARCH_ONLY"
    assert result.native_capture_provenance_verified
    assert result.reassessment_history_verified
    assert not result.research_analysis_authorized
    assert not result.current_request_checked
    state["value"] = replace(state["value"], status="blocked", research_publication_verified=False)
    capture.capture_publication_admission(
        source,
        target,
        publication_id=pin,
        request=policy.AdmissionRequest(policy.ARCHIVED_RESEARCH),
        actor_id="test",
        code_revision="test",
        initialize=False,
    )
    older = reader.read_admission_capture(target, receipt_id=first["receipt_id"])
    assert older.native_capture_provenance_verified
    assert older.reassessment_history_verified
    assert not older.pinned_receipt_is_history_head
    assert not older.research_analysis_authorized
