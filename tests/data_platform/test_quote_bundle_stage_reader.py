"""Real metadata/FS snapshots; source assembly boundary is substituted."""

import hashlib
from dataclasses import asdict, replace
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import feature_bundle as codec
from nse_quant.data_platform import quote_bundle_stage_reader as reader
from nse_quant.data_platform.gold_quote_features import ExactPriceFeature, GoldQuoteCandidate
from nse_quant.data_platform.quote_bundle_assembly import BundleAssemblyRejected
from nse_quant.data_platform.quote_bundle_staging import COMMAND, SEAL_STATE, STAGING_VERSION


def digest(value):
    return hashlib.sha256(codec.canonical(value).encode()).hexdigest()


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
    value = replace(value, build_id=digest(asdict(value)))
    encoded = codec.canonical(asdict(value))
    return codec.make_quote_bundle(
        (
            codec.QuoteBundleMember(
                value.build_id,
                codec.GOLD_READER_VERSION,
                "b" * 64,
                ("gold-job",),
                codec.digest(encoded.encode()),
                encoded,
            ),
        )
    )


@pytest.fixture
def setup(tmp_path, monkeypatch):
    sources = [duckdb.connect(":memory:") for _ in range(5)]
    stage = duckdb.connect(str(tmp_path / "staging.duckdb"))
    root = tmp_path / "artifacts"
    root.mkdir()
    stage.execute("CREATE SCHEMA gold")
    stage.execute("CREATE SCHEMA medallion_audit")
    stage.execute(
        "CREATE TABLE gold.quote_bundle_stage_schema (version INTEGER PRIMARY KEY,"
        "artifact_root VARCHAR NOT NULL)"
    )
    stage.execute("INSERT INTO gold.quote_bundle_stage_schema VALUES (1,?)", [str(root.resolve())])
    stage.execute(
        "CREATE TABLE gold.quote_bundle_stages (build_id VARCHAR PRIMARY KEY,"
        "input_revision_id VARCHAR,staging_version VARCHAR,feature_version VARCHAR,"
        "membership_fingerprint VARCHAR,manifest_hash VARCHAR,manifest_bytes BIGINT,"
        "member_count INTEGER,artifact_name VARCHAR,seal_state VARCHAR,"
        "supersedes_json VARCHAR,event_ts TIMESTAMPTZ,published_at TIMESTAMPTZ,"
        "recorded_at TIMESTAMPTZ,first_job_id VARCHAR)"
    )
    stage.execute(
        "CREATE TABLE gold.quote_bundle_stage_attempts (job_id VARCHAR PRIMARY KEY,"
        "build_id VARCHAR,recorded_at TIMESTAMPTZ)"
    )
    stage.execute("CREATE TABLE medallion_audit.schema_versions (version INTEGER PRIMARY KEY)")
    stage.execute("INSERT INTO medallion_audit.schema_versions VALUES (1)")
    stage.execute(
        "CREATE TABLE medallion_audit.dataset_contracts (dataset_name VARCHAR,"
        "contract_version VARCHAR,fingerprint VARCHAR,contract_json VARCHAR)"
    )
    stage.execute(
        "CREATE TABLE medallion_audit.jobs (job_id VARCHAR PRIMARY KEY,"
        "parent_job_id VARCHAR,command_name VARCHAR,actor_id VARCHAR,scope_ref VARCHAR,"
        "code_revision VARCHAR,config_hash VARCHAR,created_at TIMESTAMPTZ)"
    )
    stage.execute(
        "CREATE TABLE medallion_audit.job_events (job_id VARCHAR,event_index INTEGER,"
        "state VARCHAR,recorded_at TIMESTAMPTZ,reason_code VARCHAR,"
        "PRIMARY KEY(job_id,event_index))"
    )
    contract = {
        "name": "gold.quote_bundle_stages",
        "version": "1",
        "layer": "gold",
        "write_policy": "versioned_builds",
        "entity_keys": ["build_id"],
        "required_columns": ["build_id", "event_ts", "published_at", "feature_version"],
        "owner": "native_quote_bundle_staging",
    }
    stage.execute(
        "INSERT INTO medallion_audit.dataset_contracts VALUES (?,?,?,?)",
        [contract["name"], "1", digest(contract), codec.canonical(contract)],
    )
    versions = [STAGING_VERSION, codec.BUNDLE_VERSION]
    state = {"bundle": bundle(), "calls": 0, "hook": None}

    def add_attempt(value, job, status="SUCCEEDED"):
        pins = tuple(member.build_id for member in value.members)
        scope = digest([versions, pins])
        stage.execute(
            "INSERT INTO gold.quote_bundle_stage_attempts VALUES (?,?,?)",
            [job, value.bundle_id, datetime.now(UTC)],
        )
        stage.execute(
            "INSERT INTO medallion_audit.jobs VALUES (?,?,?,?,?,?,?,?)",
            [
                job,
                None,
                COMMAND,
                "test",
                "sha256:" + scope,
                "7d340d4",
                digest([versions, str(root.resolve())]),
                datetime.now(UTC),
            ],
        )
        stage.execute(
            "INSERT INTO medallion_audit.job_events VALUES (?,1,?,?,NULL)",
            [job, status, datetime.now(UTC)],
        )

    def insert(value, links=(), job="job1", status="SUCCEEDED"):
        raw = codec.encode_quote_bundle(value)
        (root / (value.bundle_id + ".json")).write_bytes(raw)
        pins = tuple(member.build_id for member in value.members)
        scope = digest([versions, pins])
        stage.execute(
            "INSERT INTO gold.quote_bundle_stages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                value.bundle_id,
                scope,
                STAGING_VERSION,
                codec.BUNDLE_VERSION,
                value.membership_fingerprint,
                value.bundle_id,
                len(raw),
                len(pins),
                value.bundle_id + ".json",
                SEAL_STATE,
                codec.canonical(links),
                None,
                None,
                datetime.now(UTC),
                job,
            ],
        )
        add_attempt(value, job, status)

    insert(state["bundle"])

    def assemble(*connections, build_ids):
        assert list(connections) == sources
        assert build_ids == tuple(member.build_id for member in state["bundle"].members)
        state["calls"] += 1
        if state["hook"] is not None:
            state["hook"]()
        return state["bundle"]

    monkeypatch.setattr(reader, "assemble_quote_bundle", assemble)

    def run(pin=state["bundle"].bundle_id, artifact_root=root):
        return reader.read_staged_quote_bundle(
            *sources, stage, bundle_id=pin, artifact_root=artifact_root
        )

    yield sources, stage, root, state, run, insert, add_attempt
    for connection in [*sources, stage]:
        connection.close()


def test_verified_current_stays_unpublished_and_unchanged(setup):
    _, stage, root, state, run, _, _ = setup
    before = stage.execute("SELECT * FROM gold.quote_bundle_stages").fetchall()
    path = root / (state["bundle"].bundle_id + ".json")
    raw = path.read_bytes()
    result = run()
    assert result.status == "verified_current"
    assert result.bundle == state["bundle"]
    assert result.successful_attempt_job_ids == ("job1",)
    assert not result.publication_asserted
    assert not result.historical_validity_asserted
    assert not result.decision_eligibility_asserted
    assert result.bundle.published_at is None
    assert path.read_bytes() == raw
    assert stage.execute("SELECT * FROM gold.quote_bundle_stages").fetchall() == before
    assert run() == result
    assert state["calls"] == 2


@pytest.mark.parametrize(
    "sql,reason",
    [
        (
            "UPDATE gold.quote_bundle_stage_schema SET version=2",
            "STAGE_SCHEMA_OR_ROOT_BINDING_NOT_VERIFIED",
        ),
        ("DELETE FROM medallion_audit.dataset_contracts", "STAGE_CONTRACT_NOT_VERIFIED"),
        (
            "UPDATE gold.quote_bundle_stages SET staging_version='bad'",
            "UNSUPPORTED_STAGE_VERSION_OR_STATE",
        ),
        (
            "UPDATE gold.quote_bundle_stages SET seal_state='PUBLISHED'",
            "UNSUPPORTED_STAGE_VERSION_OR_STATE",
        ),
        (
            "UPDATE gold.quote_bundle_stages SET manifest_hash='bad'",
            "STAGE_ARTIFACT_METADATA_MISMATCH",
        ),
        (
            "UPDATE gold.quote_bundle_stages SET artifact_name='../bad'",
            "STAGE_ARTIFACT_METADATA_MISMATCH",
        ),
        (
            "UPDATE gold.quote_bundle_stages SET manifest_bytes=0",
            "STAGE_ARTIFACT_METADATA_MISMATCH",
        ),
        ("UPDATE gold.quote_bundle_stages SET member_count=65", "STAGE_ARTIFACT_METADATA_MISMATCH"),
        (
            "UPDATE gold.quote_bundle_stages SET membership_fingerprint=repeat('f',64)",
            "STAGE_MANIFEST_METADATA_MISMATCH",
        ),
        ("UPDATE gold.quote_bundle_stages SET event_ts=now()", "UNSUPPORTED_STAGE_TEMPORAL_CLAIMS"),
        (
            "UPDATE gold.quote_bundle_stages SET published_at=now()",
            "UNSUPPORTED_STAGE_TEMPORAL_CLAIMS",
        ),
        ("DELETE FROM gold.quote_bundle_stage_attempts", "STAGE_ATTEMPT_LINEAGE_MISSING"),
        ("DELETE FROM medallion_audit.jobs", "STAGE_ATTEMPT_AUDIT_MISMATCH"),
        ("UPDATE medallion_audit.jobs SET config_hash='bad'", "STAGE_ATTEMPT_AUDIT_MISMATCH"),
        ("UPDATE medallion_audit.jobs SET actor_id=''", "STAGE_ATTEMPT_AUDIT_MISMATCH"),
        ("UPDATE medallion_audit.jobs SET code_revision=''", "STAGE_ATTEMPT_AUDIT_MISMATCH"),
        ("UPDATE medallion_audit.job_events SET state='RUNNING'", "STAGE_ATTEMPT_NOT_TERMINAL"),
        ("UPDATE medallion_audit.job_events SET state='FAILED'", "STAGE_NO_SUCCESSFUL_ATTEMPT"),
        ("UPDATE gold.quote_bundle_stages SET supersedes_json='null'", "INVALID_STAGE_HISTORY"),
        (
            "UPDATE gold.quote_bundle_stages SET supersedes_json='[true]'",
            "STAGE_INVALID_SUPERSESSION_LINK",
        ),
    ],
)
def test_bad_metadata_blocks_before_source(setup, sql, reason):
    _, stage, _, state, run, _, _ = setup
    stage.execute(sql)
    evidence = run()
    assert evidence.status == "blocked"
    assert evidence.reason_code == reason
    assert evidence.bundle is None
    assert state["calls"] == 0


def test_failed_unsupported_successor_invalidates_before_quality_filters(setup):
    _, stage, _, state, run, insert, _ = setup
    old = state["bundle"]
    changed = codec.make_quote_bundle((replace(old.members[0], evidence_fingerprint="c" * 64),))
    insert(changed, links=(old.bundle_id,), job="job2", status="FAILED")
    stage.execute(
        "UPDATE gold.quote_bundle_stages SET staging_version='unsupported' WHERE build_id=?",
        [changed.bundle_id],
    )
    assert run().reason_code == "STAGE_ASSESSMENT_SUPERSEDED"
    assert state["calls"] == 0


def test_multiple_heads_do_not_select_latest(setup):
    _, _, _, state, run, insert, _ = setup
    old = state["bundle"]
    changed = codec.make_quote_bundle((replace(old.members[0], evidence_fingerprint="c" * 64),))
    insert(changed, job="job2")
    assert run().reason_code == "STAGE_AMBIGUOUS_ACTIVE_ASSESSMENTS"


@pytest.mark.parametrize("kind", ["cycle", "dangling", "duplicate"])
def test_graph_errors(setup, kind):
    _, stage, _, state, run, _, _ = setup
    pin = state["bundle"].bundle_id
    links = ["f" * 64] if kind == "dangling" else [pin, pin] if kind == "duplicate" else [pin]
    stage.execute("UPDATE gold.quote_bundle_stages SET supersedes_json=?", [codec.canonical(links)])
    reasons = {
        "cycle": "STAGE_SUPERSESSION_CYCLE",
        "dangling": "STAGE_DANGLING_SUPERSESSION_LINK",
        "duplicate": "STAGE_DUPLICATE_SUPERSESSION_LINK",
    }
    assert run().reason_code == reasons[kind]


def test_orphan_artifact_is_not_adopted(setup):
    _, stage, root, state, run, _, _ = setup
    stage.execute("DELETE FROM gold.quote_bundle_stages")
    path = root / (state["bundle"].bundle_id + ".json")
    before = path.read_bytes()
    assert run().reason_code == "ORPHAN_ARTIFACT_REVIEW_REQUIRED"
    assert path.read_bytes() == before
    assert stage.execute("SELECT count(*) FROM gold.quote_bundle_stages").fetchone() == (0,)


def test_missing_artifact_and_root_never_recreated(setup):
    _, _, root, state, run, _, _ = setup
    path = root / (state["bundle"].bundle_id + ".json")
    path.unlink()
    assert run().reason_code == "STAGED_ARTIFACT_MISSING_REVIEW_REQUIRED"
    assert not path.exists()
    root.rmdir()
    assert run().reason_code == "STAGE_ARTIFACT_ROOT_MISSING_REVIEW_REQUIRED"
    assert not root.exists()


def test_corrupt_bytes_preserved(setup):
    _, _, root, state, run, _, _ = setup
    path = root / (state["bundle"].bundle_id + ".json")
    path.write_bytes(b"corrupt")
    assert run().reason_code == "STAGED_ARTIFACT_INVALID_REVIEW_REQUIRED"
    assert path.read_bytes() == b"corrupt"
    assert state["calls"] == 0


def test_pending_retry_blocks_even_with_success(setup):
    _, stage, _, state, run, _, add = setup
    add(state["bundle"], "job2", "RUNNING")
    assert run().reason_code == "STAGE_ATTEMPT_NOT_TERMINAL"
    stage.execute(
        "INSERT INTO medallion_audit.job_events VALUES ('job2',2,'FAILED',?,NULL)",
        [datetime.now(UTC)],
    )
    assert run().status == "verified_current"


def test_source_rejection_is_not_repair_or_partial_result(setup, monkeypatch):
    _, _, _, _, run, _, _ = setup

    def reject(*args, **kwargs):
        raise BundleAssemblyRejected("BUNDLE_MEMBER_NOT_CURRENT_CANDIDATE", "f" * 64)

    monkeypatch.setattr(reader, "assemble_quote_bundle", reject)
    result = run()
    assert result.reason_code == "STAGED_BUNDLE_SOURCE_REJECTED"
    assert result.bundle is None


def test_changed_current_source_snapshot_is_rejected(setup):
    _, _, _, state, run, _, _ = setup
    state["bundle"] = codec.make_quote_bundle(
        (replace(state["bundle"].members[0], evidence_fingerprint="c" * 64),)
    )
    assert run().reason_code == "STAGED_BUNDLE_CURRENT_EVIDENCE_CHANGED"


def test_metadata_drift_during_source_revalidation_is_detected(setup):
    _, stage, _, state, run, _, _ = setup
    state["hook"] = lambda: stage.execute("UPDATE medallion_audit.jobs SET actor_id='changed'")
    assert run().reason_code == "STAGING_METADATA_CHANGED_DURING_VERIFICATION"


def test_artifact_drift_during_source_revalidation_is_detected(setup):
    _, _, root, state, run, _, _ = setup
    path = root / (state["bundle"].bundle_id + ".json")
    state["hook"] = lambda: path.write_bytes(b"changed")
    assert run().reason_code == "STAGED_ARTIFACT_INVALID_REVIEW_REQUIRED"
    assert path.read_bytes() == b"changed"


def test_source_operational_errors_propagate(setup, monkeypatch):
    _, _, _, _, run, _, _ = setup

    def fail(*args, **kwargs):
        raise RuntimeError("source unavailable")

    monkeypatch.setattr(reader, "assemble_quote_bundle", fail)
    with pytest.raises(RuntimeError, match="source unavailable"):
        run()


@pytest.mark.parametrize("pin", ["", "A" * 64, "f" * 63])
def test_invalid_pin_before_source(setup, pin):
    _, _, _, state, run, _, _ = setup
    with pytest.raises(ValueError):
        run(pin)
    assert state["calls"] == 0


def test_limits_and_unknown_bundle(setup, monkeypatch):
    _, _, _, _, run, _, _ = setup
    assert run("f" * 64).reason_code == "STAGED_BUNDLE_NOT_FOUND"
    monkeypatch.setattr(reader, "MAX_ATTEMPTS", 0)
    assert run().reason_code == "STAGE_ATTEMPT_LIMIT"
    monkeypatch.setattr(reader, "MAX_ASSESSMENTS", 0)
    assert run().reason_code == "STAGE_HISTORY_LIMIT"


def test_wrong_root_is_not_adopted(setup, tmp_path):
    _, _, _, _, run, _, _ = setup
    other = tmp_path / "other"
    assert run(artifact_root=other).reason_code == "STAGE_SCHEMA_OR_ROOT_BINDING_NOT_VERIFIED"
    assert not other.exists()


def test_legacy_objects_fail_dedicated_database_check(setup):
    _, stage, _, state, run, _, _ = setup
    stage.execute("CREATE TABLE option_stream (id INTEGER)")
    assert run().reason_code == "DEDICATED_STAGE_DATABASE_NOT_VERIFIED"
    assert state["calls"] == 0


def test_file_backed_readonly_metadata_and_artifact_remain_unchanged(setup, tmp_path):
    sources, stage, root, state, _, _, _ = setup
    path = tmp_path / "gold.duckdb"
    escaped = str(path).replace("'", "''")
    stage.execute(f"ATTACH '{escaped}' AS export_target")
    catalog = stage.execute("SELECT current_database()").fetchone()[0]
    quoted = '"' + catalog.replace('"', '""') + '"'
    stage.execute(f"COPY FROM DATABASE {quoted} TO export_target")
    stage.execute("DETACH export_target")
    manifest = root / (state["bundle"].bundle_id + ".json")
    before_db = hashlib.sha256(path.read_bytes()).hexdigest()
    before_artifact = manifest.read_bytes()
    connection = duckdb.connect(str(path), read_only=True)
    try:
        result = reader.read_staged_quote_bundle(
            *sources, connection, bundle_id=state["bundle"].bundle_id, artifact_root=root
        )
        assert result.status == "verified_current"
    finally:
        connection.close()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before_db
    assert manifest.read_bytes() == before_artifact


def test_memory_metadata_rejected(setup):
    sources, _, root, state, _, _, _ = setup
    with (
        duckdb.connect(":memory:") as memory,
        pytest.raises(ValueError, match="FILE_BACKED_STAGING_DATABASE_REQUIRED"),
    ):
        reader.read_staged_quote_bundle(
            *sources, memory, bundle_id=state["bundle"].bundle_id, artifact_root=root
        )


def test_metadata_cannot_alias_a_source_connection(setup):
    sources, stage, root, state, _, _, _ = setup
    with pytest.raises(ValueError, match="SEPARATE_BUNDLE_STAGING_DATABASE_REQUIRED"):
        reader.read_staged_quote_bundle(
            stage, *sources[1:], stage, bundle_id=state["bundle"].bundle_id, artifact_root=root
        )


def test_no_lost_audit_obligation_after_successful_retry(setup):
    _, stage, _, state, run, _, add = setup
    stage.execute("UPDATE medallion_audit.job_events SET state='RUNNING'")
    add(state["bundle"], "job2", "SUCCEEDED")
    assert run().reason_code == "STAGE_ATTEMPT_NOT_TERMINAL"
    assert stage.execute(
        "SELECT state FROM medallion_audit.job_events WHERE job_id='job1' "
        "ORDER BY event_index DESC LIMIT 1"
    ).fetchone() == ("RUNNING",)


def test_large_corrupt_artifact_rejected_without_repair(setup):
    _, _, root, state, run, _, _ = setup
    path = root / (state["bundle"].bundle_id + ".json")
    data = b"x" * (codec.MAX_BUNDLE_BYTES + 1)
    path.write_bytes(data)
    assert run().reason_code == "STAGED_ARTIFACT_INVALID_REVIEW_REQUIRED"
    assert path.stat().st_size == len(data)
    assert state["calls"] == 0


def test_scope_tampering_cannot_hide_behind_consistent_job_metadata(setup):
    _, stage, _, state, run, _, _ = setup
    fake_scope = "f" * 64
    stage.execute("UPDATE gold.quote_bundle_stages SET input_revision_id=?", [fake_scope])
    stage.execute("UPDATE medallion_audit.jobs SET scope_ref=?", ["sha256:" + fake_scope])
    assert run().reason_code == "STAGE_MANIFEST_METADATA_MISMATCH"
    assert state["calls"] == 0


def test_oversized_history_is_bounded_before_source_work(setup):
    _, stage, _, state, run, _, _ = setup
    stage.execute("UPDATE gold.quote_bundle_stages SET supersedes_json=repeat('x',100001)")
    assert run().reason_code == "INVALID_STAGE_HISTORY"
    assert state["calls"] == 0
