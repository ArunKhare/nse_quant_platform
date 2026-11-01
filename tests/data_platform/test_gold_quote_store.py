"""Real Gold/audit transactions; candidate computation boundary is substituted."""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import gold_quote_store as store
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.gold_quote_features import (
    DEFINITION_FINGERPRINT,
    FEATURE_VERSION,
    ExactPriceFeature,
    GoldQuoteCandidate,
)

PIN = "a" * 64


def seal(candidate):
    value = asdict(replace(candidate, build_id=""))
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return replace(candidate, build_id=hashlib.sha256(encoded.encode()).hexdigest())


def candidate():
    return seal(
        GoldQuoteCandidate(
            "",
            FEATURE_VERSION,
            DEFINITION_FINGERPRINT,
            PIN,
            "candidate",
            "EXACT_PROVIDER_PRICE_FIELDS",
            source_evidence_fingerprint="b" * 64,
            source_association_fingerprint="c" * 64,
            source_frame_revision_id="d" * 64,
            source_packet_ordinal=0,
            reference_assessment_revision_id="e" * 64,
            reference_row_ordinal=0,
            reference_source_fields_hash="f" * 64,
            provider_token=257,
            price_divisor=100,
            features=(ExactPriceFeature("last_price", 12345, 100, "123.45"),),
            quality_flags=("EXCHANGE_EVENT_TIME_UNKNOWN",),
        )
    )


def rejected():
    return seal(
        GoldQuoteCandidate(
            "",
            FEATURE_VERSION,
            DEFINITION_FINGERPRINT,
            PIN,
            "blocked",
            "SOURCE_ASSESSMENT_NOT_CURRENT",
        )
    )


@pytest.fixture
def setup(monkeypatch):
    sources = [duckdb.connect(":memory:") for _ in range(4)]
    gold = duckdb.connect(":memory:")
    state = {"candidate": candidate(), "calls": 0}

    def compute(*args, assessment_revision_id):
        assert list(args) == sources
        assert assessment_revision_id == PIN
        state["calls"] += 1
        return state["candidate"]

    monkeypatch.setattr(store, "build_quote_price_candidate", compute)

    def run(**changes):
        options = {
            "assessment_revision_id": PIN,
            "actor_id": "test",
            "code_revision": "835747d",
            "initialize": True,
        }
        options.update(changes)
        return store.persist_quote_price_build(*sources, gold, **options)

    yield sources, gold, state, run
    for connection in [*sources, gold]:
        connection.close()


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def latest(conn, job):
    return conn.execute(
        "SELECT state FROM medallion_audit.job_events WHERE job_id=? "
        "ORDER BY event_index DESC LIMIT 1",
        [job],
    ).fetchone()[0]


def test_persisted_exact_values_and_unknown_times(setup):
    _, gold, _, run = setup
    receipt = run()
    assert receipt["status"] == "candidate"
    assert receipt["published"] is False
    assert latest(gold, receipt["job_id"]) == "SUCCEEDED"
    row = gold.execute(
        "SELECT result_json,event_ts,published_at,effective_from,effective_to "
        "FROM gold.quote_price_builds"
    ).fetchone()
    assert row[1:] == (None, None, None, None)
    assert json.loads(row[0])["features"][0] == {
        "name": "last_price",
        "numerator": 12345,
        "denominator": 100,
        "decimal_value": "123.45",
    }
    definition = gold.execute(
        "SELECT definition_fingerprint,definition_json FROM gold.quote_price_definitions"
    ).fetchone()
    assert hashlib.sha256(definition[1].encode()).hexdigest() == definition[0]
    contract = gold.execute(
        "SELECT contract_json FROM medallion_audit.dataset_contracts"
    ).fetchone()
    assert json.loads(contract[0])["write_policy"] == "versioned_builds"


def test_exact_retry_keeps_build_and_definition_appends_attempt(setup):
    _, gold, state, run = setup
    first, second = run(), run(initialize=False)
    assert first["build_id"] == second["build_id"]
    assert second["inserted"] is False
    assert second["job_id"] != first["job_id"]
    assert count(gold, "gold.quote_price_builds") == 1
    assert count(gold, "gold.quote_price_definitions") == 1
    assert count(gold, "gold.quote_price_build_attempts") == 2
    assert state["calls"] == 2
    assert (
        gold.execute("SELECT first_job_id FROM gold.quote_price_builds").fetchone()[0]
        == (first["job_id"])
    )


def test_blocked_build_preserves_and_invalidates_prior_candidate(setup):
    _, gold, state, run = setup
    first = run()
    state["candidate"] = rejected()
    second = run()
    assert second["status"] == "blocked"
    assert first["input_revision_id"] == second["input_revision_id"]
    assert first["build_id"] != second["build_id"]
    links = gold.execute(
        "SELECT supersedes_json FROM gold.quote_price_builds WHERE build_id=?", [second["build_id"]]
    ).fetchone()[0]
    assert json.loads(links) == [first["build_id"]]
    state["candidate"] = candidate()
    retry = run()
    assert retry["build_id"] == first["build_id"] and retry["inserted"] is False
    assert count(gold, "gold.quote_price_builds") == 2
    assert (
        gold.execute(
            "SELECT supersedes_json FROM gold.quote_price_builds WHERE build_id=?",
            [second["build_id"]],
        ).fetchone()[0]
        == links
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("assessment_revision_id", "A" * 64),
        ("actor_id", ""),
        ("code_revision", " "),
    ],
)
def test_invalid_request_before_initialization(setup, field, value):
    _, gold, state, run = setup
    with pytest.raises(ValueError):
        run(**{field: value})
    assert count(gold, "information_schema.tables") == 0
    assert state["calls"] == 0


def test_legacy_target_rejected_before_audit(setup):
    _, gold, _, run = setup
    gold.execute("CREATE TABLE option_stream (id INTEGER)")
    with pytest.raises(ValueError, match="DEDICATED_GOLD_REQUIRED"):
        run()
    assert count(gold, "information_schema.tables") == 1


def test_same_connection_rejected(setup):
    sources, _, _, _ = setup
    with pytest.raises(ValueError, match="SEPARATE_GOLD_DATABASE_REQUIRED"):
        store.persist_quote_price_build(
            *sources,
            sources[0],
            assessment_revision_id=PIN,
            actor_id="test",
            code_revision="head",
            initialize=True,
        )


def test_same_file_rejected(setup, tmp_path):
    sources, _, _, _ = setup
    path = tmp_path / "shared.duckdb"
    first = duckdb.connect(str(path))
    second = duckdb.connect(str(path))
    try:
        with pytest.raises(ValueError, match="SEPARATE_GOLD_DATABASE_REQUIRED"):
            store.persist_quote_price_build(
                first,
                *sources[1:],
                second,
                assessment_revision_id=PIN,
                actor_id="test",
                code_revision="head",
                initialize=True,
            )
        assert count(first, "information_schema.tables") == 0
    finally:
        second.close()
        first.close()


def test_definition_tampering_is_never_overwritten(setup):
    _, gold, _, run = setup
    run()
    gold.execute("UPDATE gold.quote_price_definitions SET definition_json='[]'")
    with pytest.raises(ValueError, match="FEATURE_DEFINITION_VERSION_CONTENT_MISMATCH"):
        run()
    assert gold.execute("SELECT definition_json FROM gold.quote_price_definitions").fetchone() == (
        "[]",
    )
    assert count(gold, "gold.quote_price_build_attempts") == 1


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE gold.quote_price_builds SET status='blocked'",
        "UPDATE gold.quote_price_builds SET result_json='{}'",
        "UPDATE gold.quote_price_builds SET published_at=now()",
        "UPDATE gold.quote_price_builds SET source_assessment_revision_id=repeat('f',64)",
    ],
)
def test_build_tampering_fails_exact_retry(setup, sql):
    _, gold, _, run = setup
    run()
    gold.execute(sql)
    with pytest.raises(ValueError, match="GOLD_BUILD_VERSION_CONTENT_MISMATCH"):
        run()
    assert count(gold, "gold.quote_price_build_attempts") == 1


def test_schema_mismatch_prevents_computation(setup):
    _, gold, state, run = setup
    run()
    gold.execute("UPDATE gold.quote_price_schema_versions SET version=2")
    with pytest.raises(ValueError, match="UNSUPPORTED_GOLD_QUOTE_SCHEMA"):
        run()
    assert state["calls"] == 1


def test_computation_error_audited_without_result(setup, monkeypatch):
    _, gold, _, run = setup

    def fail(*args, **kwargs):
        raise RuntimeError("private exception details")

    monkeypatch.setattr(store, "build_quote_price_candidate", fail)
    with pytest.raises(RuntimeError):
        run()
    assert count(gold, "gold.quote_price_builds") == 0
    assert count(gold, "gold.quote_price_definitions") == 0
    assert gold.execute(
        "SELECT state,reason_code FROM medallion_audit.job_events ORDER BY event_index"
    ).fetchall() == [
        ("PLANNED", None),
        ("RUNNING", None),
        ("FAILED", "EXECUTION_ERROR"),
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("build_id", "bad"),
        ("definition_fingerprint", "b" * 64),
        ("source_assessment_revision_id", "f" * 64),
        ("decision_eligibility_asserted", True),
    ],
)
def test_malformed_computation_result_rejected(setup, field, value):
    _, gold, state, run = setup
    state["candidate"] = replace(candidate(), **{field: value})
    with pytest.raises(ValueError, match="GOLD_CANDIDATE_CONTRACT_MISMATCH"):
        run()
    assert count(gold, "gold.quote_price_builds") == 0


def test_noncanonical_or_naive_time_rejected(setup):
    _, gold, state, run = setup
    state["candidate"] = seal(replace(candidate(), event_ts="2026-01-01T00:00:00"))
    with pytest.raises(ValueError, match="AWARE_FEATURE_TIME_REQUIRED"):
        run()
    assert count(gold, "gold.quote_price_builds") == 0


def test_known_event_time_is_preserved_separately_from_recording_time(setup):
    _, gold, state, run = setup
    expected = datetime(2026, 1, 1, tzinfo=UTC)

    state["candidate"] = seal(replace(candidate(), event_ts=expected.isoformat()))
    run()

    event, published = gold.execute(
        "SELECT event_ts,published_at FROM gold.quote_price_builds"
    ).fetchone()

    assert isinstance(event, datetime)
    assert event.tzinfo is not None
    assert event.utcoffset() is not None
    assert event.astimezone(UTC) == expected
    assert published is None


def test_history_bound_counts_all_statuses(setup, monkeypatch):
    _, gold, state, run = setup
    monkeypatch.setattr(store, "MAX_HISTORY", 0)
    run()
    state["candidate"] = rejected()
    with pytest.raises(ValueError, match="GOLD_BUILD_HISTORY_LIMIT"):
        run()
    assert count(gold, "gold.quote_price_builds") == 1


def test_result_size_bound_rolls_back_definition(setup, monkeypatch):
    _, gold, _, run = setup
    monkeypatch.setattr(store, "MAX_RESULT_BYTES", 1)
    with pytest.raises(ValueError, match="GOLD_CANDIDATE_RESULT_LIMIT"):
        run()
    assert count(gold, "gold.quote_price_definitions") == 0
    assert count(gold, "gold.quote_price_builds") == 0


def test_attempt_write_failure_rolls_back_new_build(setup):
    _, gold, state, run = setup
    first = run()
    gold.execute("ALTER TABLE gold.quote_price_build_attempts ADD COLUMN extra INTEGER DEFAULT 1")
    state["candidate"] = rejected()
    with pytest.raises(duckdb.Error):
        run()
    assert gold.execute("SELECT build_id FROM gold.quote_price_builds").fetchall() == [
        (first["build_id"],),
    ]
    assert count(gold, "gold.quote_price_build_attempts") == 1


def test_final_audit_failure_is_preserved_not_repaired(setup, monkeypatch):
    _, gold, _, run = setup
    original = AuditLedger.transition

    def transition(self, job, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("final audit failure")
        return original(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", transition)
    with pytest.raises(RuntimeError, match="final audit failure"):
        run()
    old_job = gold.execute("SELECT job_id FROM gold.quote_price_build_attempts").fetchone()[0]
    assert latest(gold, old_job) == "RUNNING"
    assert count(gold, "gold.quote_price_builds") == 1
    monkeypatch.setattr(AuditLedger, "transition", original)
    retry = run()
    assert retry["inserted"] is False
    assert latest(gold, old_job) == "RUNNING"
    assert latest(gold, retry["job_id"]) == "SUCCEEDED"


def test_initialize_false_never_creates_database_schema(setup):
    _, gold, state, run = setup
    with pytest.raises(duckdb.Error):
        run(initialize=False)
    assert count(gold, "information_schema.tables") == 0
    assert state["calls"] == 0


def test_definition_size_limit_before_database_initialization(setup, monkeypatch):
    _, gold, _, run = setup
    monkeypatch.setattr(store, "DEFINITION", ("x" * 32769,))
    with pytest.raises(ValueError, match="FEATURE_DEFINITION_LIMIT"):
        run()
    assert count(gold, "information_schema.tables") == 0


def test_same_feature_version_cannot_change_definition(setup, monkeypatch):
    _, gold, state, run = setup
    run()
    changed_definition = (*store.DEFINITION, "changed-without-version-bump")
    encoded = json.dumps(changed_definition, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    monkeypatch.setattr(store, "DEFINITION", changed_definition)
    monkeypatch.setattr(store, "DEFINITION_FINGERPRINT", fingerprint)
    state["candidate"] = seal(replace(candidate(), definition_fingerprint=fingerprint))
    with pytest.raises(ValueError, match="FEATURE_DEFINITION_VERSION_CONTENT_MISMATCH"):
        run()
    assert count(gold, "gold.quote_price_builds") == 1
    assert count(gold, "gold.quote_price_definitions") == 1


def test_quoted_catalog_and_gold_schema_are_unambiguous(setup, tmp_path):
    sources, gold, state, _ = setup
    path = tmp_path / "gold.fixture'quoted.duckdb"
    escaped = str(path).replace("'", "''")
    alias = '"go""ld"'
    gold.execute(f"ATTACH '{escaped}' AS {alias}")
    gold.execute('USE "go""ld"')
    receipt = store.persist_quote_price_build(
        *sources,
        gold,
        assessment_revision_id=PIN,
        actor_id="test",
        code_revision="head",
        initialize=True,
    )
    table = store._name(gold, "quote_price_builds")
    assert table.startswith('"go""ld"."gold".')
    assert gold.execute(f"SELECT build_id FROM {table}").fetchone()[0] == receipt["build_id"]
    assert state["calls"] == 1
