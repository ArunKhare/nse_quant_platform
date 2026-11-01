"""Actual writer/audit/reader integration using the existing synthetic source fixture.

Not full Bronze acquisition, issuer-authentication or source-to-decision E2E.
"""

from dataclasses import replace

import duckdb
import pytest
from test_underlying_assertion_store import registry as registry

from nse_quant.data_platform import underlying_assertion as kernel
from nse_quant.data_platform import underlying_assertion_reader as reader
from nse_quant.data_platform import underlying_assertion_store as store
from nse_quant.data_platform.audit import AuditLedger, JobState


def read(target, pin):
    return reader.read_underlying_assertion_recording(target, assertion_id=pin)


def test_verified_recording_never_means_verified_identity(registry):
    _, target, _, record = registry
    first = record()
    result = read(target, first["assertion_id"])
    assert result.status == "verified_archived_recording"
    assert result.archived_integrity_verified
    assert result.native_recording_provenance_verified
    assert result.registry_history_verified
    assert result.archived_assertion_kind == "ASSERTED"
    assert result.pinned_is_last_distinct_statement
    assert result.canonical_underlying_id is None
    assert not result.identity_verified
    assert not result.issuer_authenticated
    assert not result.current_bronze_support_checked
    assert not result.bronze_acquisition_provenance_verified
    assert not result.historical_validity_asserted
    assert not result.availability_evidence_verified
    assert not result.decision_eligibility_asserted


def test_withdrawal_and_old_retry_do_not_revive_old_statement(registry):
    _, target, claim, record = registry
    first = record()
    withdrawn = record(replace(claim, assertion="WITHDRAWN"))
    assert record()["assertion_id"] == first["assertion_id"]
    old = read(target, first["assertion_id"])
    newer = read(target, withdrawn["assertion_id"])
    assert old.registry_history_verified
    assert not old.pinned_is_last_distinct_statement
    assert old.last_distinct_statement_id == withdrawn["assertion_id"]
    assert newer.archived_assertion_kind == "WITHDRAWN"
    assert newer.native_recording_provenance_verified
    assert not newer.identity_verified


def test_registry_origin_is_verified_in_its_own_scope(registry):
    _, target, claim, record = registry
    record()
    other = record(replace(claim, external_id="OTHER_TEST_ASSET"))
    assert read(target, other["assertion_id"]).registry_history_verified


def test_exact_retry_changes_complete_evidence_fingerprint(registry):
    _, target, _, record = registry
    first = record()
    before = read(target, first["assertion_id"])
    record()
    after = read(target, first["assertion_id"])
    assert before.registry_history_verified and after.registry_history_verified
    assert before.evidence_fingerprint != after.evidence_fingerprint


def test_unlinked_failed_attempt_retained_without_success_filter(registry):
    _, target, _, record = registry
    first = record()
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=store.COMMAND,
        actor_id="test",
        code_revision="test",
        scope_ref="sha256:" + first["subject_scope_id"],
        config_hash=kernel.digest(
            [store.VERSION, store.CONTRACT_FINGERPRINT, kernel.DEFINITION_FINGERPRINT]
        ),
    )
    ledger.transition(job, JobState.FAILED, "EXECUTION_ERROR")
    result = read(target, first["assertion_id"])
    assert result.archived_integrity_verified
    assert result.native_recording_provenance_verified
    assert not result.registry_history_verified
    assert job in result.audit_obligation_job_ids
    assert result.status == "review_required"


def test_incomplete_origin_cannot_be_healed_by_later_success(registry):
    _, target, _, record = registry
    first = record()
    events = store._name(target, "medallion_audit", "job_events")
    target.execute(f"DELETE FROM {events} WHERE job_id=? AND state='SUCCEEDED'", [first["job_id"]])
    record()
    result = read(target, first["assertion_id"])
    assert result.archived_integrity_verified
    assert not result.native_recording_provenance_verified
    assert not result.registry_history_verified
    assert first["job_id"] in result.audit_obligation_job_ids


@pytest.mark.parametrize(
    "table,assignment",
    [
        ("assertions", "assertion_kind='VERIFIED'"),
        ("assertions", "assertion_bytes='bad'::BLOB"),
        ("assertions", "prior_assertion_ids_json='[true]'"),
        ("contracts", "content_json='[]'"),
        ("definitions", "fingerprint='bad'"),
    ],
)
def test_corruption_requires_review_without_writes_or_identity_upgrade(registry, table, assignment):
    _, target, _, record = registry
    first = record()
    qualified = store._name(target, "identity_evidence", table)
    target.execute(f"UPDATE {qualified} SET {assignment}")
    events = store._name(target, "medallion_audit", "job_events")
    before = target.execute(f"SELECT count(*) FROM {events}").fetchone()
    result = read(target, first["assertion_id"])
    assert result.status == "review_required"
    assert not result.registry_history_verified
    assert not result.identity_verified
    assert target.execute(f"SELECT count(*) FROM {events}").fetchone() == before


def test_failed_newer_content_is_not_filtered_to_old_asserted_row(registry):
    _, target, claim, record = registry
    first = record()
    newer = record(replace(claim, assertion="DISPUTED"))
    table = store._name(target, "identity_evidence", "assertions")
    target.execute(
        f"UPDATE {table} SET assertion_bytes='unsupported'::BLOB WHERE assertion_id=?",
        [newer["assertion_id"]],
    )
    result = read(target, first["assertion_id"])
    assert result.archived_integrity_verified
    assert not result.registry_history_verified
    assert result.status == "review_required"


def test_timezone_fingerprint_and_actual_readonly_archived_database(registry):
    _, target, _, record = registry
    first = record()
    expected = read(target, first["assertion_id"])
    target.execute("SET TimeZone='Asia/Kolkata'")
    assert read(target, first["assertion_id"]).evidence_fingerprint == expected.evidence_fingerprint
    catalog = target.execute("SELECT current_database()").fetchone()[0]
    path = next(
        row[2] for row in target.execute("PRAGMA database_list").fetchall() if row[1] == catalog
    )
    target.close()
    with duckdb.connect(":memory:") as conn:
        escaped = path.replace("'", "''")
        conn.execute(f"ATTACH '{escaped}' AS {reader._quote(catalog)} (READ_ONLY)")
        conn.execute(f"USE {reader._quote(catalog)}")
        actual = read(conn, first["assertion_id"])
        assert actual.evidence_fingerprint == expected.evidence_fingerprint


def test_missing_tables_are_review_not_initialization(tmp_path):
    with duckdb.connect(str(tmp_path / "empty.duckdb")) as conn:
        result = read(conn, "a" * 64)
        assert result.status == "review_required"
        assert conn.execute("SELECT count(*) FROM information_schema.tables").fetchone() == (0,)
