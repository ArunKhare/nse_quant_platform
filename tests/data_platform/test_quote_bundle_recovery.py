"""Read-only targeted recovery observations with actual DuckDB/filesystem fixtures."""

import builtins
import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import feature_bundle as codec
from nse_quant.data_platform import quote_bundle_recovery as recovery
from nse_quant.data_platform import quote_bundle_recovery_cli as cli
from nse_quant.data_platform.gold_quote_features import ExactPriceFeature, GoldQuoteCandidate


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
def setup(tmp_path):
    db = duckdb.connect(str(tmp_path / "staging.duckdb"))
    root = tmp_path / "artifacts"
    root.mkdir()
    db.execute("CREATE SCHEMA gold")
    db.execute("CREATE SCHEMA medallion_audit")
    db.execute(
        "CREATE TABLE gold.quote_bundle_stage_schema (version INTEGER,artifact_root VARCHAR)"
    )
    db.execute("INSERT INTO gold.quote_bundle_stage_schema VALUES (1,?)", [str(root.resolve())])
    db.execute("CREATE TABLE medallion_audit.schema_versions (version INTEGER)")
    db.execute("INSERT INTO medallion_audit.schema_versions VALUES (1)")
    db.execute(
        "CREATE TABLE gold.quote_bundle_stages (build_id VARCHAR PRIMARY KEY,"
        "input_revision_id VARCHAR,staging_version VARCHAR,feature_version VARCHAR,"
        "membership_fingerprint VARCHAR,manifest_hash VARCHAR,manifest_bytes BIGINT,"
        "member_count INTEGER,artifact_name VARCHAR,seal_state VARCHAR,"
        "supersedes_json VARCHAR,"
        "event_ts TIMESTAMPTZ,published_at TIMESTAMPTZ,recorded_at TIMESTAMPTZ,"
        "first_job_id VARCHAR)"
    )
    db.execute(
        "CREATE TABLE gold.quote_bundle_stage_attempts (job_id VARCHAR PRIMARY KEY,"
        "build_id VARCHAR,recorded_at TIMESTAMPTZ)"
    )
    db.execute(
        "CREATE TABLE medallion_audit.jobs (job_id VARCHAR PRIMARY KEY,command_name VARCHAR,"
        "scope_ref VARCHAR,config_hash VARCHAR,actor_id VARCHAR,code_revision VARCHAR)"
    )
    db.execute(
        "CREATE TABLE medallion_audit.job_events (job_id VARCHAR,event_index INTEGER,state VARCHAR)"
    )
    db.execute(
        "CREATE TABLE medallion_audit.dataset_contracts (dataset_name VARCHAR,"
        "contract_version VARCHAR,fingerprint VARCHAR,contract_json VARCHAR)"
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
    db.execute(
        "INSERT INTO medallion_audit.dataset_contracts VALUES (?,?,?,?)",
        [contract["name"], "1", digest(contract), codec.canonical(contract)],
    )
    value = bundle()
    raw = codec.encode_quote_bundle(value)
    versions = [recovery.STAGING_VERSION, codec.BUNDLE_VERSION]
    scope = digest([versions, tuple(member.build_id for member in value.members)])
    db.execute(
        "INSERT INTO gold.quote_bundle_stages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            value.bundle_id,
            scope,
            recovery.STAGING_VERSION,
            codec.BUNDLE_VERSION,
            value.membership_fingerprint,
            value.bundle_id,
            len(raw),
            1,
            value.bundle_id + ".json",
            "SEALED_NOT_PUBLISHED",
            "[]",
            None,
            None,
            datetime.now(UTC),
            "job1",
        ],
    )
    db.execute(
        "INSERT INTO gold.quote_bundle_stage_attempts VALUES (?,?,?)",
        ["job1", value.bundle_id, datetime.now(UTC)],
    )
    db.execute(
        "INSERT INTO medallion_audit.jobs VALUES (?,?,?,?,?,?)",
        [
            "job1",
            recovery.COMMAND,
            "sha256:" + scope,
            digest([versions, str(root.resolve())]),
            "test",
            "05de39c",
        ],
    )
    db.execute("INSERT INTO medallion_audit.job_events VALUES ('job1',1,'SUCCEEDED')")
    (root / (value.bundle_id + ".json")).write_bytes(raw)

    def run(**kwargs):
        return recovery.inspect_bundle_recovery(
            db, bundle_id=value.bundle_id, artifact_root=root, **kwargs
        )

    yield db, root, value, run
    db.close()


def reasons(plan):
    return {finding.reason_code for finding in plan.findings}


def test_no_target_findings_is_not_authority_or_global_clean(setup):
    _, _, _, run = setup
    plan = run()
    assert plan.status == "NO_TARGET_FINDINGS"
    assert plan.scope_complete
    assert plan.artifact_observation == "CONTENT_VALID_NOT_SOURCE_VERIFIED"
    assert not plan.execution_permitted
    assert not plan.source_current_checked
    assert not plan.global_inventory_performed
    assert not plan.publication_asserted
    assert not plan.decision_eligibility_asserted
    assert run() == plan


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("DELETE FROM gold.quote_bundle_stages", "ORPHAN_ARTIFACT_NO_ADOPTION_AUTHORITY"),
        (
            "UPDATE medallion_audit.job_events SET state='RUNNING'",
            "AUDIT_NONTERMINAL_OR_UNKNOWN_REVIEW_REQUIRED",
        ),
        (
            "UPDATE medallion_audit.job_events SET state='FAILED'",
            "FAILED_OR_CANCELLED_JOB_REVIEW_REQUIRED",
        ),
        ("DELETE FROM gold.quote_bundle_stage_attempts", "FIRST_JOB_LINK_NOT_OBSERVED"),
        ("DELETE FROM medallion_audit.jobs", "LINKED_AUDIT_JOB_NOT_OBSERVED"),
        ("UPDATE medallion_audit.jobs SET actor_id=''", "AUDIT_IDENTITY_REVIEW_REQUIRED"),
        ("UPDATE gold.quote_bundle_stages SET manifest_bytes=1", "STAGE_MANIFEST_DISAGREEMENT"),
        (
            "UPDATE gold.quote_bundle_stages SET published_at=now()",
            "STAGE_METADATA_REVIEW_REQUIRED",
        ),
        ("DELETE FROM medallion_audit.dataset_contracts", "STAGE_CONTRACT_REVIEW_REQUIRED"),
        (
            "UPDATE gold.quote_bundle_stages SET supersedes_json='bad'",
            "HISTORY_EVIDENCE_REVIEW_REQUIRED",
        ),
    ],
)
def test_review_findings_never_execute(setup, mutation, code):
    db, root, _, run = setup
    db.execute(mutation)
    files = {path.name: path.read_bytes() for path in root.iterdir()}
    before = db.execute("SELECT * FROM gold.quote_bundle_stages").fetchall()
    plan = run()
    assert code in reasons(plan)
    assert plan.status == "REVIEW_REQUIRED"
    assert not plan.execution_permitted
    assert db.execute("SELECT * FROM gold.quote_bundle_stages").fetchall() == before
    assert {path.name: path.read_bytes() for path in root.iterdir()} == files


def test_missing_and_corrupt_artifacts_not_repaired(setup):
    _, root, value, run = setup
    path = root / (value.bundle_id + ".json")
    path.unlink()
    assert "REGISTERED_ARTIFACT_MISSING" in reasons(run())
    assert not path.exists()
    path.write_bytes(b"broken")
    assert "ARTIFACT_CONTENT_REVIEW_REQUIRED" in reasons(run())
    assert path.read_bytes() == b"broken"


def test_pending_is_names_only_and_never_ingestible(setup):
    _, root, _, run = setup
    pending = root / ".pending-bundle-test"
    pending.write_bytes(b"SECRET_PENDING_PAYLOAD")
    plan = run()
    assert "PENDING_FILE_REVIEW_CANDIDATE_NOT_INGESTIBLE" in reasons(plan)
    assert len(plan.pending_file_refs) == 1
    assert "SECRET_PENDING_PAYLOAD" not in json.dumps(asdict(plan))
    assert pending.read_bytes() == b"SECRET_PENDING_PAYLOAD"


def test_root_loss_and_wrong_binding_never_create_directory(setup, tmp_path):
    db, root, value, run = setup
    (root / (value.bundle_id + ".json")).unlink()
    root.rmdir()
    assert not run().scope_complete
    assert not root.exists()
    other = tmp_path / "other"
    plan = recovery.inspect_bundle_recovery(db, bundle_id=value.bundle_id, artifact_root=other)
    assert "SCHEMA_OR_ROOT_BINDING_REVIEW_REQUIRED" in reasons(plan)
    assert not other.exists()


def test_budget_limits_never_become_all_clear(setup):
    _, root, _, run = setup
    plan = run(policy=recovery.RecoveryPolicy(max_artifact_bytes=1))
    assert plan.status == "INCOMPLETE_REVIEW_REQUIRED"
    assert plan.artifact_bytes_observed == 0
    assert plan.artifact_hash_observed is None
    (root / ".pending-bundle-extra").write_bytes(b"pending")
    plan = run(policy=recovery.RecoveryPolicy(max_directory_entries=1))
    assert not plan.directory_scan_complete
    assert not plan.scope_complete
    assert "DIRECTORY_PREFIX_COVERAGE_LIMIT" in reasons(plan)


def test_extra_audit_jobs_are_bounded(setup):
    db, _, _, run = setup
    db.execute(
        "INSERT INTO medallion_audit.jobs SELECT 'job2',command_name,scope_ref,"
        "config_hash,actor_id,code_revision FROM medallion_audit.jobs"
    )
    plan = run(policy=recovery.RecoveryPolicy(max_jobs=1))
    assert "AUDIT_COVERAGE_LIMIT" in reasons(plan)
    assert not plan.scope_complete


@pytest.mark.parametrize(
    "changes",
    [
        {"max_jobs": 0},
        {"max_directory_entries": True},
        {"max_history": 1002},
        {"max_artifact_bytes": codec.MAX_BUNDLE_BYTES + 1},
    ],
)
def test_invalid_policy(changes):
    with pytest.raises(ValueError):
        recovery.RecoveryPolicy(**changes)


def cli_arguments(path, root, value):
    return ["--staging-db", str(path), "--artifact-root", str(root), "--bundle-id", value.bundle_id]


def test_default_cli_plan_does_not_import_execution_or_create_files(tmp_path, monkeypatch, capsys):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"duckdb", "nse_quant.data_platform.quote_bundle_recovery"}:
            raise AssertionError("Plan imported execution")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    args = cli_arguments(tmp_path / "staging.duckdb", tmp_path / "artifacts", bundle())
    assert cli.main(args) == 0
    assert json.loads(capsys.readouterr().out)["execution_permitted"] is False
    assert list(tmp_path.iterdir()) == []


def test_cli_rejects_execution_and_repair_switches(tmp_path):
    args = cli_arguments(tmp_path / "staging.duckdb", tmp_path / "artifacts", bundle())
    for option in ("--execute", "--repair", "--adopt", "--initialize"):
        with pytest.raises(SystemExit):
            cli.main(args + [option])


def test_cli_reads_real_readonly_clone_and_returns_report(setup, tmp_path, capsys):
    db, root, value, _ = setup
    path = tmp_path / "readonly.duckdb"
    escaped = str(path).replace("'", "''")
    db.execute(f"ATTACH '{escaped}' AS export_target")
    db.execute("COPY FROM DATABASE staging TO export_target")
    db.execute("DETACH export_target")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert cli.main(cli_arguments(path, root, value) + ["--inspect"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "NO_TARGET_FINDINGS"
    assert not report["execution_permitted"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_bad_pin_and_missing_db_do_not_create_files(tmp_path):
    args = cli_arguments(tmp_path / "staging.duckdb", tmp_path / "artifacts", bundle())
    with pytest.raises(SystemExit):
        cli.main(args + ["--inspect"])
    args[-1] = "A" * 64
    with pytest.raises(SystemExit):
        cli.main(args)
    assert list(tmp_path.iterdir()) == []


def test_other_successful_stage_in_scope_is_not_an_orphan_job(setup):
    db, root, old, _ = setup
    new = codec.make_quote_bundle((replace(old.members[0], evidence_fingerprint="e" * 64),))
    raw = codec.encode_quote_bundle(new)
    (root / (new.bundle_id + ".json")).write_bytes(raw)
    db.execute(
        "INSERT INTO gold.quote_bundle_stages SELECT ?,input_revision_id,staging_version,"
        "feature_version,?, ?, ?,member_count,?,seal_state,?,event_ts,published_at,"
        "recorded_at,'job2' FROM gold.quote_bundle_stages WHERE build_id=?",
        [
            new.bundle_id,
            new.membership_fingerprint,
            new.bundle_id,
            len(raw),
            new.bundle_id + ".json",
            codec.canonical([old.bundle_id]),
            old.bundle_id,
        ],
    )
    db.execute(
        "INSERT INTO gold.quote_bundle_stage_attempts VALUES (?,?,?)",
        ["job2", new.bundle_id, datetime.now(UTC)],
    )
    db.execute(
        "INSERT INTO medallion_audit.jobs SELECT 'job2',command_name,scope_ref,config_hash,"
        "actor_id,code_revision FROM medallion_audit.jobs WHERE job_id='job1'"
    )
    db.execute("INSERT INTO medallion_audit.job_events VALUES ('job2',1,'SUCCEEDED')")
    plan = recovery.inspect_bundle_recovery(db, bundle_id=new.bundle_id, artifact_root=root)
    assert plan.status == "NO_TARGET_FINDINGS"
    old_plan = recovery.inspect_bundle_recovery(db, bundle_id=old.bundle_id, artifact_root=root)
    assert "HISTORY_ASSESSMENT_SUPERSEDED" in reasons(old_plan)


def test_unlinked_incomplete_stage_job_is_not_forced_success(setup):
    db, _, _, run = setup
    db.execute(
        "INSERT INTO medallion_audit.jobs SELECT 'unfinished',command_name,scope_ref,"
        "config_hash,actor_id,code_revision FROM medallion_audit.jobs"
    )
    db.execute("INSERT INTO medallion_audit.job_events VALUES ('unfinished',1,'RUNNING')")
    plan = run()
    assert "UNLINKED_STAGE_JOB_REVIEW_REQUIRED" in reasons(plan)
    assert "AUDIT_NONTERMINAL_OR_UNKNOWN_REVIEW_REQUIRED" in reasons(plan)
    assert db.execute(
        "SELECT state FROM medallion_audit.job_events WHERE job_id='unfinished'"
    ).fetchone() == ("RUNNING",)


def test_graph_cycle_and_history_limit_are_not_skipped(setup):
    db, _, value, run = setup
    db.execute(
        "UPDATE gold.quote_bundle_stages SET supersedes_json=?",
        [codec.canonical([value.bundle_id])],
    )
    assert "HISTORY_SUPERSESSION_CYCLE" in reasons(run())


def test_cli_review_exit_and_failure_redaction(setup, tmp_path, capsys, monkeypatch):
    db, root, value, _ = setup
    (root / ".pending-bundle-review").write_bytes(b"retained")
    path = tmp_path / "cli-metadata.duckdb"
    escaped = str(path).replace("'", "''")
    db.execute(f"ATTACH '{escaped}' AS export_target")
    db.execute("COPY FROM DATABASE staging TO export_target")
    db.execute("DETACH export_target")
    args = cli_arguments(path, root, value) + ["--inspect"]
    assert cli.main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REVIEW_REQUIRED"

    def fail(*args, **kwargs):
        raise RuntimeError("SECRET_EXCEPTION_BODY")

    monkeypatch.setattr(recovery, "inspect_bundle_recovery", fail)
    assert cli.main(args) == 1
    output = capsys.readouterr().out
    assert "SECRET" not in output
    assert json.loads(output)["reason_code"] == "RECOVERY_INSPECTION_FAILED"
