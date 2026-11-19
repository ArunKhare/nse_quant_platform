"""Actual synthetic legacy -> Bronze -> Silver -> Gold -> research publication.

Failure injection replaces failing boundaries, never a fabricated successful source.
"""

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime

import duckdb
import pytest
from test_legacy_market_gold_bundle_native import assemble
from test_legacy_market_gold_native import build
from test_legacy_market_gold_native import native as native
from test_legacy_market_gold_native import pipeline as pipeline
from test_legacy_market_partition_silver_native import bronze_target as bronze_target
from test_legacy_market_partition_silver_native import legacy as legacy

from nse_quant.data_platform import legacy_market_publication as service
from nse_quant.data_platform import legacy_market_publication_admission as admission
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.publication_admission import (
    ARCHIVED_RESEARCH,
    POINT_IN_TIME,
    AdmissionRequest,
)


@pytest.fixture
def publication_target(native, tmp_path):
    gold_result = build(native)
    raw = assemble(native, gold_result)
    directory = tmp_path / "publications"
    directory.mkdir()
    path = directory / "gold.duckdb"  # Real catalog/schema collision.
    with duckdb.connect(str(path)) as conn:
        service.initialize_legacy_publication(conn)
    request = service.bundle.LegacyGoldBundleRequest(
        gold_result["build_id"], gold_result["recording_fingerprint"]
    )
    return native, path, request, service.bundle.gold.sha(raw)


def publish(target, **changes):
    native, path, request, reviewed = target
    args = dict(
        request=request,
        expected_bundle_id=reviewed,
        actor_id="synthetic",
        code_revision="a" * 40,
        purpose=service.PURPOSE,
        allow_research_publication=True,
    )
    args.update(changes)
    with (
        duckdb.connect(str(native[0][1]), read_only=True) as bronze,
        duckdb.connect(str(native[0][2]), read_only=True) as silver,
        duckdb.connect(str(native[1]), read_only=True) as gold,
        duckdb.connect(str(path)) as conn,
    ):
        return service.publish_legacy_research_bundle(bronze, silver, gold, conn, **args)


def read(target, result, current=False):
    native, path, _, _ = target
    args = dict(
        publication_id=result["publication_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(path), read_only=True) as conn:
        if not current:
            return service.read_legacy_research_publication(conn, **args)
        with (
            duckdb.connect(str(native[0][1]), read_only=True) as bronze,
            duckdb.connect(str(native[0][2]), read_only=True) as silver,
            duckdb.connect(str(native[1]), read_only=True) as gold,
        ):
            return service.revalidate_legacy_research_publication(
                bronze, silver, gold, conn, **args
            )


def test_actual_publication_and_native_readers_cover_every_ordinal(publication_target):
    result = publish(publication_target)
    retained = read(publication_target, result)
    assert retained == read(publication_target, result, current=True)
    assert retained.row_count == 1001
    doc = json.loads(retained.manifest_bytes)
    assert len(doc["inputs"]) == len(doc["outputs"]) == 1001
    outputs = [json.loads(bytes.fromhex(r)) for r in doc["outputs"]]
    assert [r["source_ordinal"] for r in outputs] == list(range(1001))
    assert {r["partition_index"] for r in outputs} == {0, 1}
    assert retained.research_publication_verified
    assert not retained.current_source_checked
    assert not retained.decision_eligibility_asserted
    assert not retained.availability_verified
    assert retained.canonical_contract_id is None
    assert doc["publication_asserted"] is False
    with duckdb.connect(str(publication_target[1]), read_only=True) as conn:
        table = service.name(conn, "medallion_audit", "job_events")
        assert conn.execute(f"SELECT state FROM {table} ORDER BY event_index").fetchall() == [
            (s,) for s in ("PLANNED", "RUNNING", "STAGED", "VALIDATED", "PUBLISHED", "SUCCEEDED")
        ]


def test_actual_admission_research_and_point_in_time_and_exact_policy_replay(publication_target):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1]), read_only=True) as conn:
        args = dict(
            publication_id=result["publication_id"],
            expected_recording_fingerprint=result["recording_fingerprint"],
        )
        research = admission.assess_legacy_publication_use(
            conn, **args, request=AdmissionRequest(ARCHIVED_RESEARCH)
        )
        decision = admission.assess_legacy_publication_use(
            conn,
            **args,
            request=AdmissionRequest(POINT_IN_TIME, datetime.now(UTC), datetime.now(UTC)),
        )
    assert research.status == "ACCEPTED_RESEARCH_ONLY"
    assert research.research_analysis_permitted
    assert decision.status == "REJECTED"
    assert not decision.research_analysis_permitted
    for receipt in (research, decision):
        assert not receipt.decision_eligibility_asserted
        raw = admission.encode_legacy_admission(receipt)
        assert (
            admission.replay_legacy_admission(raw, expected_receipt_id=receipt.receipt_id)
            == receipt
        )
        with pytest.raises(ValueError):
            admission.encode_legacy_admission(replace(receipt, decision_eligibility_asserted=True))


@pytest.mark.parametrize(
    "changes",
    [
        {"allow_research_publication": False},
        {"purpose": "POINT_IN_TIME_DECISION"},
        {"actor_id": ""},
        {"code_revision": "short"},
    ],
    ids=["intent", "purpose", "actor", "revision"],
)
def test_intent_and_execution_gates(publication_target, changes):
    with pytest.raises(ValueError):
        publish(publication_target, **changes)


@pytest.mark.parametrize(
    "column,expression",
    [
        ("row_count", "1"),
        ("manifest_byte_count", "1"),
        ("manifest_bytes", "'bad'::BLOB"),
        ("feature_version", "'bad'"),
        ("purpose", "'POINT_IN_TIME_DECISION'"),
        ("clock_semantics", "'independent'"),
        ("event_ts", "current_timestamp"),
        ("effective_from", "current_timestamp"),
        ("effective_to", "current_timestamp"),
        ("decision_eligibility_asserted", "true"),
        ("first_job_id", "'bad'"),
        ("request_bytes", "'bad'::BLOB"),
        ("bundle_id", "'bad'"),
    ],
    ids=[
        "rows",
        "length",
        "bytes",
        "version",
        "purpose",
        "clock",
        "event",
        "from",
        "to",
        "decision",
        "origin",
        "request",
        "bundle",
    ],
)
def test_materialized_metadata_and_content_corruption(publication_target, column, expression):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as conn:
        table = service.name(conn, "gold", service.DOMAIN[1])
        conn.execute(f"UPDATE {table} SET {column}={expression}")
    with pytest.raises(ValueError):
        read(publication_target, result)


@pytest.mark.parametrize(
    "case",
    ["attempt", "success", "contract", "definition", "audit-version"],
    ids=["attempt", "success", "contract", "definition", "audit-version"],
)
def test_original_recording_obligations(publication_target, case):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as conn:
        if case == "attempt":
            conn.execute(f"DELETE FROM {service.name(conn, 'gold', service.DOMAIN[2])}")
        elif case == "success":
            table = service.name(conn, "medallion_audit", "job_events")
            conn.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
        elif case == "contract":
            table = service.name(conn, "medallion_audit", "dataset_contracts")
            conn.execute(f"UPDATE {table} SET fingerprint='bad'")
        elif case == "definition":
            table = service.name(conn, "gold", service.DOMAIN[0])
            conn.execute(f"UPDATE {table} SET definition='bad'::BLOB")
        else:
            table = service.name(conn, "medallion_audit", "schema_versions")
            conn.execute(f"UPDATE {table} SET version=2")
    with pytest.raises(ValueError):
        read(publication_target, result)


@pytest.mark.parametrize(
    "state",
    ["PLANNED", "RUNNING", "FAILED", "CANCELLED"],
    ids=["planned", "running", "failed", "cancelled"],
)
def test_extra_scoped_job_blocks_good_subset_and_retry(publication_target, state):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as conn:
        ledger = AuditLedger(conn)
        job = ledger.plan_job(
            command_name=service.COMMAND,
            actor_id="synthetic",
            code_revision="a" * 40,
            config_hash="b" * 64,
            scope_ref="sha256:" + service.scope_id(publication_target[2].build_id),
        )
        if state != "PLANNED":
            ledger.transition(job, JobState(state))
    with pytest.raises(ValueError):
        read(publication_target, result)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


@pytest.mark.parametrize("terminal", ["PUBLISHED", "SUCCEEDED"], ids=["published", "final-success"])
def test_post_domain_audit_failure_is_not_readable_or_adoptable(
    publication_target,
    monkeypatch,
    terminal,
):
    original = AuditLedger.transition

    def fail(self, job, state, reason_code=None):
        if state == JobState(terminal):
            raise RuntimeError("SYNTHETIC_POST_COMMIT_AUDIT")
        return original(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail)
    with pytest.raises(RuntimeError, match="POST_COMMIT"):
        publish(publication_target)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with duckdb.connect(str(publication_target[1])) as conn:
        table = service.name(conn, "gold", service.DOMAIN[1])
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (1,)
    key = service.publication_id(publication_target[2].build_id, publication_target[3])
    with pytest.raises(ValueError, match="AUDIT"):
        read(publication_target, dict(publication_id=key, recording_fingerprint="a" * 64))
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


def test_real_domain_sql_failure_rolls_back_record_and_attempt(publication_target):
    with duckdb.connect(str(publication_target[1])) as conn:
        table = service.name(conn, "gold", service.DOMAIN[2])
        conn.execute(f"ALTER TABLE {table} ADD COLUMN synthetic_failure INTEGER DEFAULT 0")
    with pytest.raises(duckdb.Error):
        publish(publication_target)
    with duckdb.connect(str(publication_target[1]), read_only=True) as conn:
        for n in service.DOMAIN[1:]:
            table = service.name(conn, "gold", n)
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


def test_bad_review_pin_leaves_failed_obligation_not_healed_by_new_pin(publication_target):
    with pytest.raises(ValueError):
        publish(publication_target, expected_bundle_id="0" * 64)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


def test_changed_recording_pin_does_not_change_first_write_scope(publication_target):
    bad = replace(publication_target[2], recording_fingerprint="0" * 64)
    with pytest.raises(ValueError):
        publish(publication_target, request=bad)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


def test_first_write_refuses_before_upstream_reader(publication_target, monkeypatch):
    publish(publication_target)

    def forbidden(*args, **kwargs):
        raise AssertionError("upstream must not be called")

    monkeypatch.setattr(service.bundle, "assemble_legacy_gold_bundle", forbidden)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


def test_orphan_attempt_prevents_adoption(publication_target, monkeypatch):
    with duckdb.connect(str(publication_target[1])) as conn:
        table = service.name(conn, "gold", service.DOMAIN[2])
        conn.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?)",
            [
                "orphan",
                service.scope_id(publication_target[2].build_id),
                publication_target[2].build_id,
                "a" * 64,
            ],
        )

    def forbidden(*args, **kwargs):
        raise AssertionError("orphan must refuse before source")

    monkeypatch.setattr(service.bundle, "assemble_legacy_gold_bundle", forbidden)
    with pytest.raises(ValueError, match="ORPHAN"):
        publish(publication_target)


def test_second_actual_assembly_failure_commits_no_domain(publication_target, monkeypatch):
    original = service.bundle.assemble_legacy_gold_bundle
    calls = 0

    def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_ASSEMBLY")
        return original(*args, **kwargs)

    monkeypatch.setattr(service.bundle, "assemble_legacy_gold_bundle", fail)
    with pytest.raises(RuntimeError, match="SECOND_ASSEMBLY"):
        publish(publication_target)
    with duckdb.connect(str(publication_target[1]), read_only=True) as conn:
        for n in service.DOMAIN[1:]:
            table = service.name(conn, "gold", n)
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


def test_retained_current_native_and_legacy_sql_are_distinct(publication_target):
    result = publish(publication_target)
    native = publication_target[0]
    with duckdb.connect(str(native[0][0])) as conn:
        table = service.name(conn, "main", "spot_candles")
        conn.execute(f"UPDATE {table} SET close=7")
    assert read(publication_target, result, current=True).row_count == 1001
    with duckdb.connect(str(native[0][1])) as conn:
        table = service.name(conn, "medallion_audit", "job_events")
        conn.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    assert read(publication_target, result).row_count == 1001
    with pytest.raises(ValueError):
        read(publication_target, result, current=True)


def test_aggregate_transfer_preflight(publication_target):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as conn:
        table = service.name(conn, "gold", service.DOMAIN[1])
        conn.execute(
            f"UPDATE {table} SET manifest_bytes=encode(repeat('x',?))",
            [service.bundle.MAX_BYTES + 1],
        )
    with pytest.raises(ValueError, match="AGGREGATE_BYTE_BOUND"):
        read(publication_target, result)


def test_request_transfer_guard(publication_target):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as conn:
        table = service.name(conn, "gold", service.DOMAIN[1])
        conn.execute(f"UPDATE {table} SET request_bytes=encode(repeat('x',513))")
    with pytest.raises(ValueError, match="REQUEST_BOUND"):
        read(publication_target, result)


def test_same_live_file_alias_preserves_parent(publication_target):
    with duckdb.connect(str(publication_target[1])) as conn:
        alias = conn.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                service.publish_legacy_research_bundle(
                    conn,
                    None,
                    None,
                    alias,
                    request=publication_target[2],
                    expected_bundle_id=publication_target[3],
                    actor_id="synthetic",
                    code_revision="a" * 40,
                    purpose=service.PURPOSE,
                    allow_research_publication=True,
                )
            assert conn.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()


def test_readonly_reader_and_no_reinitialization(publication_target):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as conn:
        with pytest.raises(ValueError, match="EMPTY"):
            service.initialize_legacy_publication(conn)
        with pytest.raises(ValueError, match="READONLY"):
            service.read_legacy_research_publication(
                conn,
                publication_id=result["publication_id"],
                expected_recording_fingerprint=result["recording_fingerprint"],
            )


def test_record_clock_drift_requires_original_recording_pin(publication_target):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as conn:
        table = service.name(conn, "gold", service.DOMAIN[1])
        conn.execute(f"UPDATE {table} SET published_at=published_at+INTERVAL 1 SECOND")
    with pytest.raises(ValueError, match="FINGERPRINT"):
        read(publication_target, result)


def test_timezone_does_not_change_recording_fingerprint(publication_target):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1]), read_only=True) as conn:
        conn.execute("SET TimeZone='Asia/Kolkata'")
        assert (
            service.read_legacy_research_publication(
                conn,
                publication_id=result["publication_id"],
                expected_recording_fingerprint=result["recording_fingerprint"],
            ).row_count
            == 1001
        )


@pytest.mark.parametrize("layer", ["bronze", "silver", "gold"], ids=["bronze", "silver", "gold"])
def test_actual_upstream_failure_cannot_publish_or_heal(publication_target, layer):
    native = publication_target[0]
    path = {"bronze": native[0][1], "silver": native[0][2], "gold": native[1]}[layer]
    with duckdb.connect(str(path)) as conn:
        table = service.name(conn, "medallion_audit", "job_events")
        conn.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    with pytest.raises(ValueError):
        publish(publication_target)
    with duckdb.connect(str(publication_target[1]), read_only=True) as conn:
        for n in service.DOMAIN[1:]:
            table = service.name(conn, "gold", n)
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


def test_admission_never_uses_old_good_when_original_audit_is_incomplete(publication_target):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as conn:
        table = service.name(conn, "medallion_audit", "job_events")
        conn.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    with (
        duckdb.connect(str(publication_target[1]), read_only=True) as conn,
        pytest.raises(ValueError),
    ):
        admission.assess_legacy_publication_use(
            conn,
            publication_id=result["publication_id"],
            expected_recording_fingerprint=result["recording_fingerprint"],
            request=AdmissionRequest(ARCHIVED_RESEARCH),
        )


def test_request_pin_and_manifest_are_not_independent_mutable_metadata(publication_target):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as conn:
        table = service.name(conn, "gold", service.DOMAIN[1])
        changed = replace(publication_target[2], recording_fingerprint="0" * 64)
        conn.execute(
            f"UPDATE {table} SET request_bytes=?", [service.bundle.gold.canonical(asdict(changed))]
        )
    with pytest.raises(ValueError, match="MEMBERSHIP"):
        read(publication_target, result)


def test_native_gold_coverage_drift_blocks_publication(publication_target):
    native = publication_target[0]
    with duckdb.connect(str(native[1])) as conn:
        table = service.name(conn, "gold", "legacy_price_features")
        conn.execute(f"DELETE FROM {table} WHERE ordinal=1000")
    with pytest.raises(ValueError):
        publish(publication_target)


def test_oversized_original_actor_is_guarded_before_transfer(publication_target):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as conn:
        table = service.name(conn, "medallion_audit", "jobs")
        conn.execute(f"UPDATE {table} SET actor_id=repeat('x',129)")
    with pytest.raises(ValueError, match="AUDIT"):
        read(publication_target, result)
