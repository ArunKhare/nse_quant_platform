"""Actual synthetic window publication -> refusal-only native producer and recording."""

import json
from dataclasses import replace
from datetime import UTC, datetime

import duckdb
import pytest
from test_legacy_candle_returns_native import returns_target as returns_target
from test_legacy_market_gold_native import native as native
from test_legacy_market_gold_native import pipeline as pipeline
from test_legacy_market_partition_silver_native import bronze_target as bronze_target
from test_legacy_market_partition_silver_native import legacy as legacy
from test_legacy_return_window_native import window_target as window_target
from test_legacy_window_publication_native import publication_target as publication_target
from test_legacy_window_publication_native import publish

from nse_quant.data_platform import legacy_window_admission as admission
from nse_quant.data_platform import native_window_refusal as kernel
from nse_quant.data_platform import native_window_refusal_store as store
from nse_quant.data_platform.audit import AuditLedger, JobState


@pytest.fixture
def refusal_target(publication_target, tmp_path):
    publication = publish(publication_target)
    path = tmp_path / "native_decisions.duckdb"  # Actual catalog/schema collision.
    with duckdb.connect(str(path)) as c:
        store.initialize_window_refusal_store(c)
    at = datetime(2026, 1, 1, tzinfo=UTC)
    request = kernel.RefusalRequest(
        "synthetic-window-refusal",
        publication["publication_id"],
        publication["recording_fingerprint"],
        at,
        at,
        "a" * 40,
        kill_switch="INACTIVE",
    )
    return publication_target, path, request


def record(target, **changes):
    publication_target, path, request = target
    args = dict(request=request, actor_id="synthetic")
    args.update(changes)
    with (
        duckdb.connect(str(publication_target[1]), read_only=True) as source,
        duckdb.connect(str(path)) as c,
    ):
        return store.record_window_refusal(source, c, **args)


def read(target, result, current=False):
    args = dict(
        decision_id=result["decision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(target[1]), read_only=True) as c:
        if not current:
            return store.read_window_refusal_recording(c, **args)
        with duckdb.connect(str(target[0][1]), read_only=True) as publication:
            return store.revalidate_window_refusal(publication, c, **args)


def test_actual_complete_native_chain_stops_at_point_in_time_admission(refusal_target):
    result = record(refusal_target)
    archived = read(refusal_target, result)
    value = kernel.replay_window_refusal_entry(
        archived.entry_bytes, expected_decision_id=result["decision_id"]
    )
    outcome = value["result"]
    assert outcome["failed_stage"] == "publication_admission"
    assert outcome["admission_observed"]
    assert outcome["reason_codes"][0] == "WINDOW_POINT_IN_TIME_ADMISSION_REJECTED"
    assert [s["status"] for s in outcome["stage_trace"]] == [
        "PASSED",
        "PASSED",
        "BLOCKED",
        "NOT_RUN",
        "NOT_RUN",
        "NOT_RUN",
        "NOT_RUN",
    ]
    assert all(i["state"] == "NOT_ADMITTED" for i in outcome["input_inventory"])
    receipts = value["frozen_input"]["admission_receipts_hex"]
    assert len(receipts) == 2 and receipts[0] == receipts[1]
    receipt_raw = bytes.fromhex(receipts[0])
    receipt = admission.replay_window_admission(
        receipt_raw, expected_receipt_id=kernel.sha(receipt_raw)
    )
    frozen = json.loads(receipt.frozen_input_json)
    assert frozen["source"]["row_count"] == 1001
    assert receipt.policy_status == "REJECTED"
    assert not receipt.decision_eligibility_asserted
    assert not outcome["strategy_evaluated"] and not outcome["order_emitted"]
    assert read(refusal_target, result, current=True)["current_publication_checked"]


def test_early_refusal_recording_does_not_probe_source(tmp_path):
    path = tmp_path / "native_decisions.duckdb"
    at = datetime.now(UTC)
    request = kernel.RefusalRequest("early", "a" * 64, "b" * 64, at, at, "a" * 40)

    class ForbiddenSource:
        def __getattribute__(self, _name):
            raise AssertionError("early source was probed")

    with duckdb.connect(str(path)) as c:
        store.initialize_window_refusal_store(c)
        result = store.record_window_refusal(
            ForbiddenSource(), c, request=request, actor_id="synthetic"
        )
    with duckdb.connect(str(path), read_only=True) as c:
        archived = store.read_window_refusal_recording(
            c,
            decision_id=result["decision_id"],
            expected_recording_fingerprint=result["recording_fingerprint"],
        )
    entry = kernel.replay_window_refusal_entry(
        archived.entry_bytes, expected_decision_id=result["decision_id"]
    )
    assert entry["result"]["failed_stage"] == "kill_switch"
    assert not entry["result"]["admission_observed"]


@pytest.mark.parametrize(
    "column,value",
    [
        ("entry_bytes", "'bad'::BLOB"),
        ("entry_byte_count", "1"),
        ("failed_stage", "'strategy'"),
        ("status", "'APPROVED'"),
        ("publication_id", "'bad'"),
        ("first_job_id", "'bad'"),
    ],
    ids=["bytes", "length", "stage", "status", "publication", "origin"],
)
def test_materialized_content_and_scalar_corruption(refusal_target, column, value):
    result = record(refusal_target)
    with duckdb.connect(str(refusal_target[1])) as c:
        table = store.name(c, "native_decisions", store.DOMAIN[1])
        c.execute(f"UPDATE {table} SET {column}={value}")
    with pytest.raises(ValueError):
        read(refusal_target, result)


@pytest.mark.parametrize(
    "case",
    ["link", "audit", "definition", "audit-version"],
    ids=["link", "audit", "definition", "audit-version"],
)
def test_original_recording_obligations(refusal_target, case):
    result = record(refusal_target)
    with duckdb.connect(str(refusal_target[1])) as c:
        if case == "link":
            c.execute(f"DELETE FROM {store.name(c, 'native_decisions', store.DOMAIN[2])}")
        elif case == "audit":
            table = store.name(c, "medallion_audit", "job_events")
            c.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
        elif case == "definition":
            table = store.name(c, "native_decisions", store.DOMAIN[0])
            c.execute(f"UPDATE {table} SET definition='bad'::BLOB")
        else:
            table = store.name(c, "medallion_audit", "schema_versions")
            c.execute(f"UPDATE {table} SET version=2")
    with pytest.raises(ValueError):
        read(refusal_target, result)


def test_wrong_publication_pin_is_failed_job_not_fabricated_refusal(refusal_target):
    bad = replace(refusal_target[2], expected_publication_evidence_fingerprint="0" * 64)
    with pytest.raises(ValueError):
        record(refusal_target, request=bad)
    with duckdb.connect(str(refusal_target[1]), read_only=True) as c:
        table = store.name(c, "native_decisions", store.DOMAIN[1])
        assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        record(refusal_target)


def test_first_write_blocks_source_before_assessment(refusal_target, monkeypatch):
    record(refusal_target)

    def forbidden(*args, **kwargs):
        raise AssertionError("source must not be assessed")

    monkeypatch.setattr(admission, "assess_window_publication_use", forbidden)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        record(refusal_target)


def test_orphan_link_blocks_before_source(refusal_target):
    key = store.attempt_key(kernel.common.request_document(refusal_target[2]))
    with duckdb.connect(str(refusal_target[1])) as c:
        table = store.name(c, "native_decisions", store.DOMAIN[2])
        c.execute(f"INSERT INTO {table} VALUES (?,?,?)", ["orphan", key, "a" * 64])
    with pytest.raises(ValueError, match="ORPHAN"):
        record(refusal_target)


@pytest.mark.parametrize(
    "state",
    ["PLANNED", "RUNNING", "FAILED", "CANCELLED"],
    ids=["planned", "running", "failed", "cancelled"],
)
def test_extra_scoped_job_not_filtered_as_good_subset(refusal_target, state):
    result = record(refusal_target)
    key = store.attempt_key(kernel.common.request_document(refusal_target[2]))
    with duckdb.connect(str(refusal_target[1])) as c:
        ledger = AuditLedger(c)
        job = ledger.plan_job(
            command_name=store.COMMAND,
            actor_id="synthetic",
            code_revision="a" * 40,
            scope_ref="sha256:" + key,
            config_hash="b" * 64,
        )
        if state != "PLANNED":
            ledger.transition(job, JobState(state))
    with pytest.raises(ValueError):
        read(refusal_target, result)


def test_domain_sql_failure_rolls_back_decision_and_link(refusal_target):
    with duckdb.connect(str(refusal_target[1])) as c:
        table = store.name(c, "native_decisions", store.DOMAIN[2])
        c.execute(f"ALTER TABLE {table} ADD COLUMN synthetic_failure INTEGER DEFAULT 0")
    with pytest.raises(duckdb.Error):
        record(refusal_target)
    with duckdb.connect(str(refusal_target[1]), read_only=True) as c:
        for n in store.DOMAIN[1:]:
            table = store.name(c, "native_decisions", n)
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        record(refusal_target)


def test_final_audit_failure_after_domain_never_adoptable(refusal_target, monkeypatch):
    original = AuditLedger.transition

    def fail(self, job, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT")
        return original(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail)
    with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
        record(refusal_target)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with duckdb.connect(str(refusal_target[1]), read_only=True) as c:
        table = store.name(c, "native_decisions", store.DOMAIN[1])
        row = c.execute(f"SELECT decision_id FROM {table}").fetchone()
        assert row is not None
        with pytest.raises(ValueError, match="AUDIT"):
            store.read_window_refusal_recording(
                c, decision_id=row[0], expected_recording_fingerprint="a" * 64
            )
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        record(refusal_target)


def test_second_actual_admission_error_no_partial_decision(refusal_target, monkeypatch):
    original = admission.assess_window_publication_use
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_ADMISSION")
        return original(*args, **kwargs)

    monkeypatch.setattr(admission, "assess_window_publication_use", observe)
    with pytest.raises(RuntimeError, match="SECOND_ADMISSION"):
        record(refusal_target)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        record(refusal_target)


def test_admission_drift_is_retained_refusal_not_positive_lane(refusal_target, monkeypatch):
    """Injected post-read summary drift, not authentic changed-source evidence or full E2E."""
    original = admission.assess_window_publication_use
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = original(*args, **kwargs)
        if calls == 2:
            frozen = json.loads(result.frozen_input_json)
            frozen["source"]["recording_fingerprint"] = "0" * 64
            return admission._evaluate(admission.publication.native._canonical(frozen))
        return result

    monkeypatch.setattr(admission, "assess_window_publication_use", observe)
    result = record(refusal_target)
    entry = kernel.replay_window_refusal_entry(
        read(refusal_target, result).entry_bytes, expected_decision_id=result["decision_id"]
    )
    assert entry["result"]["reason_codes"] == ["WINDOW_ADMISSION_FULL_OBSERVATION_DRIFT"]
    assert not entry["result"]["strategy_evaluated"]


def test_retained_refusal_current_publication_and_current_upstream_distinct(refusal_target):
    result = record(refusal_target)
    publication_target = refusal_target[0]
    with duckdb.connect(str(publication_target[0][1])) as windows:
        table = store.name(windows, "medallion_audit", "job_events")
        windows.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    assert read(refusal_target, result).original_recording_verified
    assert read(refusal_target, result, current=True)["current_publication_checked"]
    with duckdb.connect(str(publication_target[1])) as publications:
        table = store.name(publications, "medallion_audit", "job_events")
        publications.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    assert read(refusal_target, result).original_recording_verified
    with pytest.raises(ValueError):
        read(refusal_target, result, current=True)


def test_entry_aggregate_sql_bound_before_transfer(refusal_target):
    result = record(refusal_target)
    with duckdb.connect(str(refusal_target[1])) as c:
        table = store.name(c, "native_decisions", store.DOMAIN[1])
        c.execute(f"UPDATE {table} SET entry_bytes=encode(repeat('x',?))", [kernel.MAX_BYTES + 1])
    with pytest.raises(ValueError, match="AGGREGATE_BYTE_BOUND"):
        read(refusal_target, result)


def test_timezone_readonly_original_recording_pin(refusal_target):
    result = record(refusal_target)
    args = dict(
        decision_id=result["decision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(refusal_target[1]), read_only=True) as c:
        c.execute("SET TimeZone='Asia/Kolkata'")
        assert store.read_window_refusal_recording(c, **args).original_recording_verified
    with duckdb.connect(str(refusal_target[1])) as c:
        with pytest.raises(ValueError, match="READONLY"):
            store.read_window_refusal_recording(c, **args)
        with pytest.raises(ValueError, match="EMPTY"):
            store.initialize_window_refusal_store(c)


def test_same_live_file_alias_preserves_owner(refusal_target):
    with duckdb.connect(str(refusal_target[1])) as c:
        alias = c.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                store.record_window_refusal(
                    c, alias, request=refusal_target[2], actor_id="synthetic"
                )
            assert c.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()
