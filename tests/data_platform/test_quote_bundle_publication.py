"""Real publication/audit transactions; verified staging reader boundary substituted."""

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import feature_bundle as codec
from nse_quant.data_platform import quote_bundle_publication as publisher
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.gold_quote_features import ExactPriceFeature, GoldQuoteCandidate
from nse_quant.data_platform.quote_bundle_stage_reader import StagedQuoteBundleEvidence

STAMP = "c" * 64


def bundle():
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
    return codec.make_quote_bundle(
        (
            codec.QuoteBundleMember(
                value.build_id,
                codec.GOLD_READER_VERSION,
                "b" * 64,
                ("gold-job",),
                codec.digest(raw.encode()),
                raw,
            ),
        )
    )


@pytest.fixture
def setup(tmp_path, monkeypatch):
    sources = [duckdb.connect(":memory:") for _ in range(6)]
    target = duckdb.connect(str(tmp_path / "publications.duckdb"))
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    value = bundle()
    original = codec.encode_quote_bundle(value)
    (artifacts / (value.bundle_id + ".json")).write_bytes(original)
    evidence = StagedQuoteBundleEvidence(
        "staged-quote-bundle-consumer@1",
        value.bundle_id,
        "verified_current",
        "STAGE_AND_SOURCES_RECOMPUTED",
        (value.bundle_id,),
        ("stage-job",),
        value,
        STAMP,
    )
    state = {"evidence": evidence, "calls": 0, "second": None}

    def verify(*connections, bundle_id, artifact_root):
        assert list(connections) == sources
        assert bundle_id == value.bundle_id
        assert artifact_root == artifacts.resolve()
        state["calls"] += 1
        if state["calls"] == 2 and state["second"] is not None:
            return state["second"]
        return state["evidence"]

    monkeypatch.setattr(publisher, "read_staged_quote_bundle", verify)

    def run(**changes):
        kwargs = {
            "bundle_id": value.bundle_id,
            "artifact_root": artifacts,
            "expected_stage_evidence_fingerprint": STAMP,
            "purpose": "RESEARCH_ONLY",
            "actor_id": "test",
            "code_revision": "fe4853d",
            "allow_publication": True,
            "initialize": True,
        }
        kwargs.update(changes)
        return publisher.publish_research_quote_bundle(*sources, target, **kwargs)

    yield sources, target, artifacts, value, state, run
    for connection in [*sources, target]:
        connection.close()


def count(target, table):
    return target.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_publication_snapshot_clock_and_legitimate_lifecycle(setup):
    _, target, root, value, state, run = setup
    raw = codec.encode_quote_bundle(value)
    result = run()
    assert result["status"] == "PUBLISHED_RESEARCH_ONLY"
    assert result["purpose"] == "RESEARCH_ONLY"
    assert result["decision_eligibility_asserted"] is False
    assert result["historical_validity_asserted"] is False
    assert state["calls"] == 2
    stored = target.execute(
        "SELECT manifest_bytes,published_at,effective_from,effective_to,"
        "event_ts FROM gold.quote_bundle_publications"
    ).fetchone()
    assert bytes(stored[0]) == raw
    assert stored[1].astimezone(UTC).isoformat() == result["published_at"]
    assert stored[2:] == (None, None, None)
    assert (root / (value.bundle_id + ".json")).read_bytes() == raw
    assert json.loads(raw)["publication_asserted"] is False
    assert target.execute(
        "SELECT state FROM medallion_audit.job_events ORDER BY event_index"
    ).fetchall() == [
        ("PLANNED",),
        ("RUNNING",),
        ("STAGED",),
        ("VALIDATED",),
        ("PUBLISHED",),
        ("SUCCEEDED",),
    ]


def test_exact_retry_preserves_original_clock_and_first_approval(setup):
    _, target, _, _, state, run = setup
    first = run()
    state["evidence"] = replace(state["evidence"], evidence_fingerprint="d" * 64)
    second = run(expected_stage_evidence_fingerprint="d" * 64, initialize=False)
    assert first["publication_id"] == second["publication_id"]
    assert first["published_at"] == second["published_at"]
    assert second["inserted"] is False
    assert count(target, "gold.quote_bundle_publications") == 1
    assert count(target, "gold.quote_publication_attempts") == 2
    assert target.execute(
        "SELECT first_stage_evidence_fingerprint FROM gold.quote_bundle_publications"
    ).fetchone() == (STAMP,)


@pytest.mark.parametrize(
    "change",
    [
        {"purpose": "DECISION_READY"},
        {"purpose": ""},
        {"allow_publication": False},
        {"bundle_id": "BAD"},
        {"expected_stage_evidence_fingerprint": "BAD"},
        {"actor_id": ""},
        {"code_revision": " "},
    ],
)
def test_intent_errors_before_database_initialization(setup, change):
    _, target, _, _, state, run = setup
    with pytest.raises(ValueError):
        run(**change)
    assert count(target, "information_schema.tables") == 0
    assert state["calls"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "blocked"},
        {"reader_version": "unknown"},
        {"evidence_fingerprint": "d" * 64},
        {"active_bundle_ids": ()},
        {"publication_asserted": True},
        {"bundle": None},
    ],
)
def test_noncurrent_or_unreviewed_stage_never_published(setup, changes):
    _, target, _, _, state, run = setup
    state["evidence"] = replace(state["evidence"], **changes)
    with pytest.raises(ValueError, match="REVIEWED_STAGE_EVIDENCE_NOT_CURRENT"):
        run()
    assert count(target, "gold.quote_bundle_publications") == 0
    assert count(target, "gold.quote_publication_attempts") == 0


def test_second_stage_check_rejects_drift(setup):
    _, target, _, _, state, run = setup
    state["second"] = replace(state["evidence"], evidence_fingerprint="d" * 64)
    with pytest.raises(ValueError):
        run()
    assert count(target, "gold.quote_bundle_publications") == 0
    assert target.execute(
        "SELECT state FROM medallion_audit.job_events ORDER BY event_index DESC LIMIT 1"
    ).fetchone() == ("FAILED",)


def test_domain_attempt_failure_rolls_back_publication_record(setup):
    _, target, _, _, _, run = setup
    first = run()
    target.execute("ALTER TABLE gold.quote_publication_attempts ADD COLUMN extra INTEGER DEFAULT 1")
    with pytest.raises(duckdb.Error):
        run()
    assert count(target, "gold.quote_bundle_publications") == 1
    assert count(target, "gold.quote_publication_attempts") == 1
    assert target.execute("SELECT build_id FROM gold.quote_bundle_publications").fetchone() == (
        first["publication_id"],
    )


def test_final_audit_failure_does_not_auto_repair_publication(setup, monkeypatch):
    _, target, _, _, _, run = setup
    original = AuditLedger.transition

    def transition(self, job, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("final audit unavailable")
        return original(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", transition)
    with pytest.raises(RuntimeError):
        run()
    assert count(target, "gold.quote_bundle_publications") == 1
    assert target.execute(
        "SELECT state FROM medallion_audit.job_events ORDER BY event_index DESC LIMIT 1"
    ).fetchone() == ("PUBLISHED",)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with pytest.raises(ValueError, match="PUBLICATION_AUDIT_REVIEW_REQUIRED"):
        run()
    assert count(target, "gold.quote_publication_attempts") == 1


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE gold.quote_bundle_publications SET manifest_bytes='wrong'::BLOB",
        "UPDATE gold.quote_bundle_publications SET purpose='DECISION_READY'",
        "UPDATE gold.quote_bundle_publications SET effective_from=now()",
        "UPDATE gold.quote_bundle_publications SET decision_eligibility_asserted=True",
    ],
)
def test_existing_content_cannot_be_overwritten(setup, sql):
    _, target, _, _, _, run = setup
    run()
    target.execute(sql)
    with pytest.raises(ValueError, match="PUBLICATION_CONTENT_MISMATCH"):
        run()
    assert count(target, "gold.quote_publication_attempts") == 1


def test_legacy_or_other_gold_store_rejected(setup):
    _, target, _, _, state, run = setup
    target.execute("CREATE TABLE option_stream (id INTEGER)")
    with pytest.raises(ValueError, match="DEDICATED_PUBLICATION_DATABASE_REQUIRED"):
        run()
    assert state["calls"] == 0
    assert count(target, "information_schema.tables") == 1


def test_output_must_not_alias_a_source(setup):
    sources, target, root, value, _, _ = setup
    with pytest.raises(ValueError, match="SEPARATE_PUBLICATION_DATABASE_REQUIRED"):
        publisher.publish_research_quote_bundle(
            target,
            *sources[1:],
            target,
            bundle_id=value.bundle_id,
            artifact_root=root,
            expected_stage_evidence_fingerprint=STAMP,
            purpose="RESEARCH_ONLY",
            actor_id="test",
            code_revision="head",
            allow_publication=True,
            initialize=True,
        )


def test_retry_timestamp_handles_non_utc_session(setup):
    _, target, _, _, _, run = setup
    target.execute("SET TimeZone='Asia/Kolkata'")
    first = run()
    assert run()["published_at"] == first["published_at"]
    instant = datetime.fromisoformat(first["published_at"])
    assert instant.tzinfo is not None
    offset = instant.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0


def test_policy_version_change_requires_review(setup, monkeypatch):
    _, target, _, _, _, run = setup
    monkeypatch.setattr(publisher, "POLICY_VERSION", "research-only-publication-policy@2")
    with pytest.raises(ValueError, match="UNSUPPORTED_RESEARCH_PUBLICATION_POLICY"):
        run()
    assert count(target, "information_schema.tables") == 0


def test_first_publication_link_failure_rolls_back_all_domain_rows(setup, monkeypatch):
    _, target, _, _, _, run = setup
    original = publisher.read_staged_quote_bundle
    calls = []

    def verify(*args, **kwargs):
        calls.append(1)
        value = original(*args, **kwargs)
        if len(calls) == 2:
            target.execute(
                "ALTER TABLE gold.quote_publication_attempts ADD COLUMN extra INTEGER DEFAULT 1"
            )
        return value

    monkeypatch.setattr(publisher, "read_staged_quote_bundle", verify)
    with pytest.raises(duckdb.Error):
        run()
    assert count(target, "gold.quote_bundle_publications") == 0
    assert count(target, "gold.quote_publication_attempts") == 0
    assert target.execute(
        "SELECT count(*) FROM medallion_audit.job_events WHERE state='PUBLISHED'"
    ).fetchone() == (0,)


def test_cannot_bypass_separate_source_reader_with_recovery_plan(setup):
    _, target, _, _, state, run = setup
    state["evidence"] = replace(state["evidence"], status="NO_TARGET_FINDINGS")
    with pytest.raises(ValueError, match="REVIEWED_STAGE_EVIDENCE_NOT_CURRENT"):
        run()
    assert count(target, "gold.quote_bundle_publications") == 0


def test_quoted_publication_catalog_uses_fully_qualified_objects(setup, tmp_path):
    _, target, _, _, _, run = setup
    path = tmp_path / "gold.duckdb"
    escaped = str(path).replace("'", "''")
    alias = '"pu""b"'
    target.execute(f"ATTACH '{escaped}' AS {alias}")
    target.execute(f"USE {alias}")
    first = run()
    second = run()
    assert first["publication_id"] == second["publication_id"]
    table = publisher._name(target, "quote_bundle_publications")
    assert table.startswith('"pu""b"."gold".')
    assert target.execute(f"SELECT count(*) FROM {table}").fetchone() == (1,)


def test_attempt_bound_does_not_bypass_review(setup, monkeypatch):
    _, target, _, _, _, run = setup
    run()
    monkeypatch.setattr(publisher, "MAX_ATTEMPTS", 0)
    with pytest.raises(ValueError, match="PUBLICATION_ATTEMPT_REVIEW_REQUIRED"):
        run()
    assert count(target, "gold.quote_publication_attempts") == 1


def test_publication_phase_failure_leaves_failed_not_authoritative_record(setup, monkeypatch):
    _, target, _, _, _, run = setup
    original = AuditLedger.transition

    def transition(self, job, state, reason_code=None):
        if state == JobState.PUBLISHED:
            raise RuntimeError("publication audit unavailable")
        return original(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", transition)
    with pytest.raises(RuntimeError):
        run()
    assert count(target, "gold.quote_bundle_publications") == 1
    assert target.execute(
        "SELECT state FROM medallion_audit.job_events ORDER BY event_index DESC LIMIT 1"
    ).fetchone() == ("FAILED",)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with pytest.raises(ValueError, match="PUBLICATION_AUDIT_REVIEW_REQUIRED"):
        run()
    assert count(target, "gold.quote_publication_attempts") == 1
