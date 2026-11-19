"""Real synthetic publication fixtures -> actual audited admission capture/revalidation."""

import json
from dataclasses import replace
from datetime import UTC, datetime

import duckdb
import pytest
from test_legacy_market_gold_native import native as native
from test_legacy_market_gold_native import pipeline as pipeline
from test_legacy_market_partition_silver_native import bronze_target as bronze_target
from test_legacy_market_partition_silver_native import legacy as legacy
from test_legacy_market_publication_native import publication_target as publication_target
from test_legacy_market_publication_native import publish

from nse_quant.data_platform import legacy_market_admission_capture as store
from nse_quant.data_platform import legacy_market_admission_revalidation as current
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.publication_admission import (
    ARCHIVED_RESEARCH,
    POINT_IN_TIME,
    AdmissionRequest,
)


@pytest.fixture
def capture_target(publication_target, tmp_path):
    publication_result = publish(publication_target)
    pins = store.LegacyAdmissionPins(
        publication_result["publication_id"], publication_result["recording_fingerprint"]
    )
    path = tmp_path / "decision_inputs.duckdb"  # Actual catalog/schema collision.
    with duckdb.connect(str(path)) as conn:
        store.initialize_legacy_admission_capture(conn)
    return publication_target, path, pins


def capture(target, **changes):
    publication_target, path, pins = target
    args = dict(
        pins=pins,
        request=AdmissionRequest(ARCHIVED_RESEARCH),
        actor_id="synthetic",
        code_revision="a" * 40,
    )
    args.update(changes)
    with (
        duckdb.connect(str(publication_target[1]), read_only=True) as source,
        duckdb.connect(str(path)) as conn,
    ):
        return store.capture_legacy_publication_use(source, conn, **args)


def read(target, result, level="retained"):
    publication_target, path, _pins = target
    args = dict(
        capture_id=result["capture_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(path), read_only=True) as conn:
        if level == "retained":
            return store.read_legacy_admission_capture(conn, **args)
        with duckdb.connect(str(publication_target[1]), read_only=True) as source:
            if level == "publication":
                return current.revalidate_legacy_admission_capture(source, conn, **args)
            native = publication_target[0]
            with (
                duckdb.connect(str(native[0][1]), read_only=True) as bronze,
                duckdb.connect(str(native[0][2]), read_only=True) as silver,
                duckdb.connect(str(native[1]), read_only=True) as gold,
            ):
                return current.revalidate_legacy_admission_upstream(
                    bronze, silver, gold, source, conn, **args
                )


def test_actual_full_native_chain_and_exact_captured_replay(capture_target):
    result = capture(capture_target)
    archived = read(capture_target, result)
    replayed = store.policy.replay_legacy_admission(
        archived.receipt_bytes, expected_receipt_id=archived.receipt_id
    )
    assert replayed.status == archived.policy_status == "ACCEPTED_RESEARCH_ONLY"
    assert archived.native_capture_recording_verified
    assert not archived.current_publication_checked
    assert not archived.research_analysis_authorized
    assert not archived.decision_eligibility_asserted
    publication = read(capture_target, result, "publication")
    assert publication.current_publication_checked
    assert not publication.current_native_upstream_checked
    upstream = read(capture_target, result, "upstream")
    assert upstream.current_native_upstream_checked
    assert upstream.exact_receipt_reproduced
    assert not upstream.research_analysis_authorized
    assert not upstream.decision_eligibility_asserted
    frozen = json.loads(replayed.frozen_input_json)
    assert frozen["source"]["row_count"] == 1001


def test_rejected_point_in_time_is_valid_capture_not_positive_lane(capture_target):
    at = datetime.now(UTC)
    result = capture(capture_target, request=AdmissionRequest(POINT_IN_TIME, at, at))
    assert result["status"] == "REJECTED"
    assert read(capture_target, result).policy_status == "REJECTED"
    for level in ("publication", "upstream"):
        observed = read(capture_target, result, level)
        assert observed.status == "matched_rejected_input"
        assert not observed.decision_eligibility_asserted
        assert not observed.research_analysis_authorized


@pytest.mark.parametrize(
    "column,expression",
    [
        ("status", "'ACCEPTED_DECISION'"),
        ("receipt_id", "'bad'"),
        ("receipt_bytes", "'bad'::BLOB"),
        ("receipt_byte_count", "1"),
        ("reason_codes_bytes", "'bad'::BLOB"),
        ("research_analysis_permitted", "false"),
        ("decision_eligibility_asserted", "true"),
        ("first_job_id", "'bad'"),
        ("publication_id", "'bad'"),
        ("publication_recording_fingerprint", "'bad'"),
    ],
    ids=[
        "status",
        "id",
        "bytes",
        "length",
        "reasons",
        "research",
        "decision",
        "origin",
        "publication",
        "recording",
    ],
)
def test_full_materialized_scalar_and_content_corruption(capture_target, column, expression):
    result = capture(capture_target)
    with duckdb.connect(str(capture_target[1])) as conn:
        table = store.name(conn, "decision_inputs", store.DOMAIN[1])
        conn.execute(f"UPDATE {table} SET {column}={expression}")
    with pytest.raises(ValueError):
        read(capture_target, result)


@pytest.mark.parametrize(
    "case",
    ["attempt", "audit", "definition", "audit-version"],
    ids=["attempt", "audit", "definition", "audit-version"],
)
def test_original_recording_obligations(capture_target, case):
    result = capture(capture_target)
    with duckdb.connect(str(capture_target[1])) as conn:
        if case == "attempt":
            conn.execute(f"DELETE FROM {store.name(conn, 'decision_inputs', store.DOMAIN[2])}")
        elif case == "audit":
            table = store.name(conn, "medallion_audit", "job_events")
            conn.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
        elif case == "definition":
            table = store.name(conn, "decision_inputs", store.DOMAIN[0])
            conn.execute(f"UPDATE {table} SET definition='bad'::BLOB")
        else:
            table = store.name(conn, "medallion_audit", "schema_versions")
            conn.execute(f"UPDATE {table} SET version=2")
    with pytest.raises(ValueError):
        read(capture_target, result)


@pytest.mark.parametrize(
    "state",
    ["PLANNED", "RUNNING", "FAILED", "CANCELLED"],
    ids=["planned", "running", "failed", "cancelled"],
)
def test_unlinked_scoped_job_not_hidden_by_good_capture(capture_target, state):
    result = capture(capture_target)
    scope = store.scope_id(capture_target[2].publication_id, AdmissionRequest(ARCHIVED_RESEARCH))
    with duckdb.connect(str(capture_target[1])) as conn:
        ledger = AuditLedger(conn)
        job = ledger.plan_job(
            command_name=store.COMMAND,
            actor_id="synthetic",
            code_revision="a" * 40,
            scope_ref="sha256:" + scope,
            config_hash="b" * 64,
        )
        if state != "PLANNED":
            ledger.transition(job, JobState(state))
    with pytest.raises(ValueError):
        read(capture_target, result)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        capture(capture_target)


def test_failed_review_pin_scope_cannot_be_healed(capture_target):
    bad = replace(capture_target[2], recording_fingerprint="0" * 64)
    with pytest.raises(ValueError):
        capture(capture_target, pins=bad)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        capture(capture_target)


def test_final_audit_failure_after_domain_commit_is_blocker(capture_target, monkeypatch):
    original = AuditLedger.transition

    def fail(self, job, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT")
        return original(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail)
    with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
        capture(capture_target)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with duckdb.connect(str(capture_target[1]), read_only=True) as conn:
        table = store.name(conn, "decision_inputs", store.DOMAIN[1])
        row = conn.execute(f"SELECT capture_id FROM {table}").fetchone()
        assert row is not None
        with pytest.raises(ValueError, match="AUDIT"):
            store.read_legacy_admission_capture(
                conn, capture_id=row[0], expected_recording_fingerprint="a" * 64
            )
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        capture(capture_target)


def test_domain_sql_failure_rolls_back_receipt_and_link(capture_target):
    with duckdb.connect(str(capture_target[1])) as conn:
        table = store.name(conn, "decision_inputs", store.DOMAIN[2])
        conn.execute(f"ALTER TABLE {table} ADD COLUMN synthetic_failure INTEGER DEFAULT 0")
    with pytest.raises(duckdb.Error):
        capture(capture_target)
    with duckdb.connect(str(capture_target[1]), read_only=True) as conn:
        for n in store.DOMAIN[1:]:
            table = store.name(conn, "decision_inputs", n)
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        capture(capture_target)


def test_second_actual_assessment_failure_no_partial_capture(capture_target, monkeypatch):
    original = store.policy.assess_legacy_publication_use
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_ASSESSMENT")
        return original(*args, **kwargs)

    monkeypatch.setattr(store.policy, "assess_legacy_publication_use", observe)
    with pytest.raises(RuntimeError, match="SECOND_ASSESSMENT"):
        capture(capture_target)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        capture(capture_target)


def test_first_write_blocks_before_source_assessment(capture_target, monkeypatch):
    capture(capture_target)

    def forbidden(*args, **kwargs):
        raise AssertionError("source must not be called")

    monkeypatch.setattr(store.policy, "assess_legacy_publication_use", forbidden)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        capture(capture_target)


def test_orphan_link_blocks_before_source(capture_target):
    scope = store.scope_id(capture_target[2].publication_id, AdmissionRequest(ARCHIVED_RESEARCH))
    with duckdb.connect(str(capture_target[1])) as conn:
        table = store.name(conn, "decision_inputs", store.DOMAIN[2])
        conn.execute(f"INSERT INTO {table} VALUES (?,?,?)", ["orphan", scope, "a" * 64])
    with pytest.raises(ValueError, match="ORPHAN"):
        capture(capture_target)


@pytest.mark.parametrize(
    "column,size,code",
    [
        ("receipt_bytes", 32769, "AGGREGATE_BYTE_BOUND"),
        ("request_bytes", 513, "TRANSFER_BOUND"),
        ("reason_codes_bytes", 4097, "TRANSFER_BOUND"),
    ],
    ids=["receipt-aggregate", "request-cell", "reason-cell"],
)
def test_sql_resource_preflight_and_independent_guards(capture_target, column, size, code):
    result = capture(capture_target)
    with duckdb.connect(str(capture_target[1])) as conn:
        table = store.name(conn, "decision_inputs", store.DOMAIN[1])
        conn.execute(f"UPDATE {table} SET {column}=encode(repeat('x',?))", [size])
    with pytest.raises(ValueError, match=code):
        read(capture_target, result)


def test_retained_capture_publication_and_current_upstream_are_distinct(capture_target):
    result = capture(capture_target)
    native = capture_target[0][0]
    with duckdb.connect(str(native[0][0])) as conn:
        table = store.name(conn, "main", "spot_candles")
        conn.execute(f"UPDATE {table} SET close=7")
    assert read(capture_target, result, "upstream").current_native_upstream_checked
    with duckdb.connect(str(native[0][1])) as conn:
        table = store.name(conn, "medallion_audit", "job_events")
        conn.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    assert read(capture_target, result).native_capture_recording_verified
    assert read(capture_target, result, "publication").current_publication_checked
    with pytest.raises(ValueError):
        read(capture_target, result, "upstream")
    with duckdb.connect(str(capture_target[0][1])) as conn:
        table = store.name(conn, "medallion_audit", "job_events")
        conn.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    assert read(capture_target, result).native_capture_recording_verified
    with pytest.raises(ValueError):
        read(capture_target, result, "publication")


def test_recording_clock_drift_requires_original_pin(capture_target):
    result = capture(capture_target)
    with duckdb.connect(str(capture_target[1])) as conn:
        table = store.name(conn, "decision_inputs", store.DOMAIN[1])
        conn.execute(f"UPDATE {table} SET recorded_at=recorded_at+INTERVAL 1 SECOND")
    with pytest.raises(ValueError, match="FINGERPRINT"):
        read(capture_target, result)


def test_timezone_and_readonly_and_no_reinitialization(capture_target):
    result = capture(capture_target)
    args = dict(
        capture_id=result["capture_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(capture_target[1]), read_only=True) as conn:
        conn.execute("SET TimeZone='Asia/Kolkata'")
        assert store.read_legacy_admission_capture(conn, **args).receipt_id == result["receipt_id"]
    with duckdb.connect(str(capture_target[1])) as conn:
        with pytest.raises(ValueError, match="READONLY"):
            store.read_legacy_admission_capture(conn, **args)
        with pytest.raises(ValueError, match="EMPTY"):
            store.initialize_legacy_admission_capture(conn)


def test_same_live_file_alias_preserves_owner(capture_target):
    with duckdb.connect(str(capture_target[1])) as conn:
        alias = conn.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                store.capture_legacy_publication_use(
                    conn,
                    alias,
                    pins=capture_target[2],
                    request=AdmissionRequest(ARCHIVED_RESEARCH),
                    actor_id="synthetic",
                    code_revision="a" * 40,
                )
            assert conn.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()


def test_independent_producer_receipt_bound_before_domain_commit(capture_target, monkeypatch):
    monkeypatch.setattr(store.policy, "encode_legacy_admission", lambda _: b"x" * 32769)
    with pytest.raises(ValueError, match="OBSERVED_RECEIPT_BYTE_BOUND"):
        capture(capture_target)
    with duckdb.connect(str(capture_target[1]), read_only=True) as conn:
        for n in store.DOMAIN[1:]:
            table = store.name(conn, "decision_inputs", n)
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
