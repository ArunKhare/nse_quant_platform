"""Actual native AuditLedger/domain transactions with synthetic Bronze-shaped rows.

Not full Bronze ingestion/provenance, independent issuer validation or native E2E.
"""

import hashlib
from dataclasses import replace

import duckdb
import pytest

from nse_quant.data_platform import underlying_assertion as kernel
from nse_quant.data_platform import underlying_assertion_store as store
from nse_quant.data_platform.audit import AuditLedger, JobState


@pytest.fixture(params=["identity_evidence", "odd'catalog\"name"])
def registry(tmp_path, request):
    payload = b"synthetic identity support"
    source = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    source.execute("CREATE SCHEMA bronze")
    source_table = store._name(source, "bronze", "event_variants")
    source.execute(
        f"CREATE TABLE {source_table} (capture_event_id VARCHAR,"
        "envelope_hash VARCHAR,payload_hash VARCHAR,payload BLOB,envelope_json VARCHAR,"
        "source VARCHAR,capture_session_id VARCHAR,source_record_id VARCHAR)"
    )
    envelope = dict(
        envelope_version=1,
        source="test_identity_support",
        capture_session_id="test-session",
        source_record_id="artifact",
        received_at="2026-01-01T00:00:00+00:00",
        payload_hash=hashlib.sha256(payload).hexdigest(),
        payload_format="bytes",
        origin_kind="test_fixture",
        exchange_ts=None,
        provider_event_id=None,
        instrument_ref=None,
    )
    event_id = kernel.digest(
        [envelope[k] for k in ("source", "capture_session_id", "source_record_id")]
    )
    envelope_hash = kernel.digest(envelope)
    source.execute(
        f"INSERT INTO {source_table} VALUES (?,?,?,?,?,?,?,?)",
        [
            event_id,
            envelope_hash,
            envelope["payload_hash"],
            payload,
            kernel.canonical(envelope),
            envelope["source"],
            envelope["capture_session_id"],
            envelope["source_record_id"],
        ],
    )
    source.close()
    bronze = duckdb.connect(str(tmp_path / "bronze.duckdb"), read_only=True)
    target = duckdb.connect(":memory:")
    path = str(tmp_path / "identity.duckdb").replace("'", "''")
    alias = '"' + request.param.replace('"', '""') + '"'
    target.execute(f"ATTACH '{path}' AS {alias}")
    target.execute(f"USE {alias}")
    claim = kernel.UnderlyingAssertionRequest(
        "TEST_NAMESPACE",
        "TEST_ASSET",
        "INDEX",
        "TEST_ISSUER",
        "ASSERTED",
        event_id,
        envelope_hash,
        envelope["payload_hash"],
        0,
        len(payload),
        hashlib.sha256(payload).hexdigest(),
        "SYNTHETIC_TEST_ONLY",
    )

    def record(value=None, **changes):
        return store.record_underlying_assertion(
            bronze,
            target,
            request=claim if value is None else value,
            actor_id="test",
            code_revision="c4104f0",
            initialize=True,
            **changes,
        )

    yield bronze, target, claim, record
    bronze.close()
    target.close()


def count(target, table):
    name = store._name(target, "identity_evidence", table)
    return target.execute(f"SELECT count(*) FROM {name}").fetchone()[0]


def test_audited_unverified_record_exact_retry_and_timezone(registry):
    _, target, _, record = registry
    target.execute("SET TimeZone='Asia/Kolkata'")
    first, retry = record(), record()
    assert first["assertion_id"] == retry["assertion_id"]
    assert first["job_id"] != retry["job_id"]
    assert retry["inserted"] is False
    assert first["identity_verified"] is False
    assert first["canonical_underlying_id"] is None
    assert count(target, "assertions") == 1
    assert count(target, "attempts") == 2
    assert count(target, "definitions") == 1
    events = store._name(target, "medallion_audit", "job_events")
    assert target.execute(
        f"SELECT state FROM {events} WHERE job_id=? ORDER BY event_index", [first["job_id"]]
    ).fetchall() == [("PLANNED",), ("RUNNING",), ("SUCCEEDED",)]


def test_withdrawal_retained_old_retry_does_not_revive_links(registry):
    _, target, claim, record = registry
    first = record()
    withdrawn = record(replace(claim, assertion="WITHDRAWN"))
    assert record()["assertion_id"] == first["assertion_id"]
    table = store._name(target, "identity_evidence", "assertions")
    links = target.execute(
        f"SELECT prior_assertion_ids_json FROM {table} WHERE assertion_id=?",
        [withdrawn["assertion_id"]],
    ).fetchone()[0]
    assert kernel.strict_json(links) == [first["assertion_id"]]
    assert count(target, "assertions") == 2


def test_support_failure_is_failed_job_not_verified_or_business_rejection(registry):
    _, target, claim, record = registry
    with pytest.raises(ValueError, match="FRAGMENT_HASH"):
        record(replace(claim, evidence_fragment_sha256="f" * 64))
    assert count(target, "assertions") == count(target, "attempts") == 0
    assert count(target, "definitions") == count(target, "contracts") == 0
    events = store._name(target, "medallion_audit", "job_events")
    last = target.execute(
        f"SELECT state FROM {events} ORDER BY event_index DESC LIMIT 1"
    ).fetchone()
    assert last == ("FAILED",)


def test_attempt_failure_rolls_back_contract_definition_assertion(registry, monkeypatch):
    _, target, _, record = registry
    original = store._support

    def support(*args, **kwargs):
        original(*args, **kwargs)
        table = store._name(target, "identity_evidence", "attempts")
        target.execute(f"ALTER TABLE {table} ADD COLUMN extra INTEGER DEFAULT 1")

    monkeypatch.setattr(store, "_support", support)
    with pytest.raises(duckdb.Error):
        record()
    assert count(target, "assertions") == count(target, "attempts") == 0
    assert count(target, "definitions") == count(target, "contracts") == 0


def test_final_audit_failure_preserved_after_successful_retry(registry, monkeypatch):
    _, target, _, record = registry
    original = AuditLedger.transition

    def transition(self, job, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("audit unavailable")
        return original(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", transition)
    with pytest.raises(RuntimeError):
        record()
    table = store._name(target, "identity_evidence", "assertions")
    first_job = target.execute(f"SELECT first_job_id FROM {table}").fetchone()[0]
    monkeypatch.setattr(AuditLedger, "transition", original)
    retry = record()
    assert retry["inserted"] is False
    events = store._name(target, "medallion_audit", "job_events")
    state = target.execute(
        f"SELECT state FROM {events} WHERE job_id=? ORDER BY event_index DESC LIMIT 1",
        [first_job],
    ).fetchone()
    assert state == ("RUNNING",)


@pytest.mark.parametrize(
    "table,assignment",
    [
        ("contracts", "content_json='[]'"),
        ("definitions", "content_json='[]'"),
        ("assertions", "assertion_kind='VERIFIED'"),
        ("assertions", "assertion_bytes='bad'::BLOB"),
    ],
)
def test_existing_content_never_overwritten(registry, table, assignment):
    _, target, _, record = registry
    record()
    name = store._name(target, "identity_evidence", table)
    target.execute(f"UPDATE {name} SET {assignment}")
    with pytest.raises(ValueError):
        record()
    assert count(target, "attempts") == 1


def test_legacy_target_and_source_alias_rejected(registry):
    bronze, target, claim, record = registry
    target.execute("CREATE TABLE option_stream(id INTEGER)")
    with pytest.raises(ValueError, match="DEDICATED"):
        record()
    with pytest.raises(ValueError, match="SEPARATE"):
        store.record_underlying_assertion(
            bronze,
            bronze,
            request=claim,
            actor_id="test",
            code_revision="test",
            initialize=True,
        )
