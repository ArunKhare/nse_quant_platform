"""Actual assembly/audit/SQL with lower source kernel substituted; not native E2E.

Supplied for local QA; not run in the delivery sandbox.
"""

import pytest
from test_gold_quote_reader import setup as setup
from test_native_research_iv_bundle_boundary import bundle_case as bundle_case
from test_native_research_option_boundary import scenario as scenario
from test_research_iv_revalidation_boundary import revalidation_case as revalidation_case
from test_research_iv_store_boundary import archive_case as archive_case

from nse_quant.data_platform import native_research_iv_bundle as native
from nse_quant.data_platform import research_iv_bundle_store as store
from nse_quant.data_platform.audit import AuditLedger, JobState


@pytest.fixture
def writer(bundle_case, revalidation_case, tmp_path):
    import duckdb

    _, requests, archive, _, _, _ = bundle_case
    _, _, _, _, _, _, _, sources, gold = revalidation_case
    target = duckdb.connect(str(tmp_path / "bundle-output.duckdb"))

    def persist(selected=None, initialize=False):
        return store.persist_research_iv_bundle(
            *sources,
            gold,
            archive,
            target,
            requests=requests if selected is None else selected,
            actor_id="synthetic-reviewer",
            code_revision="synthetic-test",
            initialize=initialize,
        )

    yield target, requests, persist, sources, gold, archive
    target.close()


def test_actual_assembly_archive_roundtrip_and_exact_retry(writer):
    target, _, persist, _, _, _ = writer
    first = persist(initialize=True)
    saved = store.read_research_iv_bundle_archive(target, build_id_pin=first["build_id"])
    assert saved.status == "verified_archived_head"
    assert saved.recorded_result_status == "assembled_current_research_iv_bundle"
    assert saved.archived_recording_verified is True
    assert saved.current_source_checked is False
    assert saved.publication_asserted is False
    assert saved.decision_eligibility_asserted is False
    table = store._name(target, "gold", store.DOMAIN_TABLES[2])
    original = target.execute(f"SELECT * FROM {table}").fetchall()
    second = persist()
    assert second["build_id"] == first["build_id"]
    assert second["inserted"] is False
    assert second["job_id"] != first["job_id"]
    assert target.execute(f"SELECT * FROM {table}").fetchall() == original
    later = store.read_research_iv_bundle_archive(target, build_id_pin=first["build_id"])
    assert later.evidence_fingerprint != saved.evidence_fingerprint


def test_review_required_result_is_archived_not_published(writer):
    target, requests, persist, _, _, _ = writer
    bad = (native.IvBundleRequest(requests[0].build_id, "0" * 64),)
    receipt = persist(bad, initialize=True)
    saved = store.read_research_iv_bundle_archive(target, build_id_pin=receipt["build_id"])
    assert saved.recorded_result_status == "review_required"
    assert saved.status == "verified_archived_head"
    assert '"bundle":null' in saved.result_json
    assert saved.publication_asserted is False


def test_failed_final_audit_blocks_read_and_retry(writer, monkeypatch):
    target, _, persist, _, _, _ = writer
    real = AuditLedger.transition

    def fail_completion(self, job_id, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT_FAILURE")
        return real(self, job_id, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail_completion)
    with pytest.raises(RuntimeError, match="SYNTHETIC_FINAL_AUDIT_FAILURE"):
        persist(initialize=True)
    table = store._name(target, "gold", store.DOMAIN_TABLES[2])
    row = target.execute(f"SELECT build_id FROM {table}").fetchone()
    assert row is not None
    with pytest.raises(store.IvBundleArchiveReviewRequired):
        store.read_research_iv_bundle_archive(target, build_id_pin=row[0])
    monkeypatch.setattr(AuditLedger, "transition", real)
    with pytest.raises(store.IvBundleArchiveReviewRequired):
        persist()


def test_domain_failure_rolls_back_all_domain_objects(writer, monkeypatch):
    target, _, persist, _, _, _ = writer

    def forbidden(self, contract):
        raise RuntimeError("SYNTHETIC_CONTRACT_FAILURE")

    monkeypatch.setattr(AuditLedger, "register_contract", forbidden)
    with pytest.raises(RuntimeError, match="SYNTHETIC_CONTRACT_FAILURE"):
        persist(initialize=True)
    for name in store.DOMAIN_TABLES[1:]:
        assert target.execute(
            f"SELECT count(*) FROM {store._name(target, 'gold', name)}"
        ).fetchone() == (0,)
    contracts = store._name(target, "medallion_audit", "dataset_contracts")
    assert target.execute(f"SELECT count(*) FROM {contracts}").fetchone() == (0,)
    events = store._name(target, "medallion_audit", "job_events")
    assert target.execute(f"SELECT state FROM {events} ORDER BY event_index").fetchall() == [
        ("PLANNED",),
        ("RUNNING",),
        ("FAILED",),
    ]


def test_definition_origin_is_verified_in_its_own_scope(writer):
    target, requests, persist, _, _, _ = writer
    first = persist((requests[0],), initialize=True)
    second = persist((requests[1],))
    store.read_research_iv_bundle_archive(target, build_id_pin=second["build_id"])
    events = store._name(target, "medallion_audit", "job_events")
    target.execute(f"DELETE FROM {events} WHERE job_id=? AND event_index=3", [first["job_id"]])
    with pytest.raises(store.IvBundleArchiveReviewRequired):
        store.read_research_iv_bundle_archive(target, build_id_pin=second["build_id"])


def test_duplicate_requests_fail_before_initialization_or_assembly(writer, monkeypatch):
    target, requests, persist, _, _, _ = writer

    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected assembly")

    monkeypatch.setattr(native, "assemble_native_research_iv_bundle", forbidden)
    with pytest.raises(ValueError, match="UNIQUE_SORTED"):
        persist((requests[0], requests[0]), initialize=True)
    assert target.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_catalog=current_database()"
    ).fetchone() == (0,)


def test_distinct_cursor_same_file_target_is_rejected(writer):
    target, requests, _, sources, gold, _ = writer
    cursor = target.cursor()
    assert cursor is not target
    row = target.execute("SELECT current_database()").fetchone()
    assert row is not None
    cursor.execute('USE "' + str(row[0]).replace('"', '""') + '"')
    try:
        with pytest.raises(ValueError, match="SEPARATE_IV_BUNDLE_ARCHIVE_OUTPUT"):
            store.persist_research_iv_bundle(
                *sources,
                gold,
                cursor,
                target,
                requests=requests,
                actor_id="synthetic-reviewer",
                code_revision="synthetic-test",
                initialize=True,
            )
        assert target.execute("SELECT 1").fetchone() == (1,)
    finally:
        cursor.close()
