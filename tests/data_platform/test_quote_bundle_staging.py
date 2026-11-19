"""Real artifact/DB/audit tests, substituting only source bundle assembly."""

import json
from dataclasses import asdict, replace

import duckdb
import pytest

from nse_quant.data_platform import bundle_artifacts as artifact_module
from nse_quant.data_platform import feature_bundle as codec
from nse_quant.data_platform import quote_bundle_staging as service
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bundle_artifacts import BundleArtifacts
from nse_quant.data_platform.gold_quote_features import ExactPriceFeature, GoldQuoteCandidate


def bundle():
    candidate = GoldQuoteCandidate(
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
    candidate = replace(
        candidate, build_id=codec.digest(codec.canonical(asdict(candidate)).encode())
    )
    encoded = codec.canonical(asdict(candidate))
    member = codec.QuoteBundleMember(
        candidate.build_id,
        codec.GOLD_READER_VERSION,
        "b" * 64,
        ("gold-job-1",),
        codec.digest(encoded.encode()),
        encoded,
    )
    return codec.make_quote_bundle((member,))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    sources = [duckdb.connect(":memory:") for _ in range(5)]
    target = duckdb.connect(str(tmp_path / "staging.duckdb"))
    artifacts = tmp_path / "artifacts"
    state = {"bundle": bundle(), "calls": 0}

    def assemble(*connections, build_ids):
        assert list(connections) == sources
        assert build_ids == tuple(member.build_id for member in state["bundle"].members)
        state["calls"] += 1
        return state["bundle"]

    monkeypatch.setattr(service, "assemble_quote_bundle", assemble)

    def run(connection=target, **changes):
        options = {
            "build_ids": tuple(member.build_id for member in state["bundle"].members),
            "artifact_root": artifacts,
            "actor_id": "test",
            "code_revision": "2b29bc4",
            "initialize": True,
        }
        options.update(changes)
        return service.stage_quote_bundle(*sources, connection, **options)

    yield sources, target, artifacts, state, run
    for connection in [*sources, target]:
        connection.close()


def count(target, table):
    return target.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def latest(target, job):
    return target.execute(
        "SELECT state FROM medallion_audit.job_events WHERE job_id=? "
        "ORDER BY event_index DESC LIMIT 1",
        [job],
    ).fetchone()[0]


def test_atomic_metadata_and_exact_verified_artifact(setup):
    _, target, root, state, run = setup
    receipt = run()
    raw = codec.encode_quote_bundle(state["bundle"])
    assert (root / (receipt["bundle_id"] + ".json")).read_bytes() == raw
    assert receipt["status"] == "SEALED_NOT_PUBLISHED"
    assert receipt["published"] is False
    assert receipt["decision_eligibility_asserted"] is False
    assert latest(target, receipt["job_id"]) == "SUCCEEDED"
    assert count(target, "gold.quote_bundle_stages") == 1
    assert count(target, "gold.quote_bundle_stage_attempts") == 1
    assert target.execute(
        "SELECT event_ts,published_at FROM gold.quote_bundle_stages"
    ).fetchone() == (
        None,
        None,
    )
    assert not list(root.glob(".pending-bundle-*"))
    assert count(target, "medallion_audit.dataset_contracts") == 1
    assert target.execute(
        "SELECT count(*) FROM medallion_audit.job_events WHERE state='PUBLISHED'"
    ).fetchone() == (0,)


def test_exact_retry_reverifies_without_rewriting_file(setup, monkeypatch):
    _, target, root, state, run = setup
    first = run()
    path = root / (first["bundle_id"] + ".json")
    before = path.stat().st_mtime_ns

    def fail(*args, **kwargs):
        raise AssertionError("Exact retry must not write/link artifacts")

    monkeypatch.setattr(BundleArtifacts, "write_new", fail)
    second = run(initialize=False)
    assert first["bundle_id"] == second["bundle_id"]
    assert second["inserted"] is False
    assert first["job_id"] != second["job_id"]
    assert state["calls"] == 2
    assert path.stat().st_mtime_ns == before
    assert count(target, "gold.quote_bundle_stage_attempts") == 2


def test_no_silent_orphan_adoption(setup):
    _, target, root, state, run = setup
    value = state["bundle"]
    BundleArtifacts(root).write_new(codec.encode_quote_bundle(value), bundle_id=value.bundle_id)
    before = (root / (value.bundle_id + ".json")).read_bytes()
    with pytest.raises(ValueError, match="ORPHAN_BUNDLE_ARTIFACT_REVIEW_REQUIRED"):
        run()
    assert count(target, "gold.quote_bundle_stages") == 0
    assert (root / (value.bundle_id + ".json")).read_bytes() == before


def test_registered_missing_artifact_is_not_automatically_resealed(setup):
    _, target, root, _, run = setup
    first = run()
    path = root / (first["bundle_id"] + ".json")
    path.unlink()
    with pytest.raises(ValueError, match="STAGED_ARTIFACT_MISSING_REVIEW_REQUIRED"):
        run()
    assert not path.exists()
    assert count(target, "gold.quote_bundle_stage_attempts") == 1


def test_corrupt_existing_bytes_are_preserved_not_overwritten(setup):
    _, target, root, _, run = setup
    first = run()
    path = root / (first["bundle_id"] + ".json")
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        run()
    assert path.read_bytes() == b"corrupt"
    assert count(target, "gold.quote_bundle_stage_attempts") == 1


def test_root_binding_cannot_change_silently(setup, tmp_path):
    _, target, _, _, run = setup
    run()
    other = tmp_path / "other-artifacts"
    with pytest.raises(ValueError, match="STAGING_SCHEMA_OR_ROOT_BINDING_MISMATCH"):
        run(artifact_root=other)
    assert not other.exists()
    assert count(target, "gold.quote_bundle_stage_attempts") == 1


def test_metadata_tampering_detected_without_file_changes(setup):
    _, target, root, _, run = setup
    first = run()
    path = root / (first["bundle_id"] + ".json")
    raw = path.read_bytes()
    target.execute("UPDATE gold.quote_bundle_stages SET manifest_bytes=1")
    with pytest.raises(ValueError, match="STAGED_BUNDLE_CONTENT_MISMATCH"):
        run()
    assert path.read_bytes() == raw


def test_domain_failure_leaves_orphan_and_retry_requires_review(setup):
    _, target, root, state, run = setup
    first = run()
    old = state["bundle"]
    member = replace(old.members[0], evidence_fingerprint="c" * 64)
    state["bundle"] = codec.make_quote_bundle((member,))

    class FaultConnection:
        def execute(self, sql, *args, **kwargs):
            if sql.lstrip().startswith("INSERT INTO") and '"quote_bundle_stage_attempts"' in sql:
                raise RuntimeError("injected attempt failure")
            return target.execute(sql, *args, **kwargs)

    with pytest.raises(RuntimeError, match="injected attempt failure"):
        run(connection=FaultConnection())
    orphan = root / (state["bundle"].bundle_id + ".json")
    assert orphan.exists()
    assert count(target, "gold.quote_bundle_stages") == 1
    assert target.execute("SELECT build_id FROM gold.quote_bundle_stages").fetchone() == (
        first["bundle_id"],
    )
    with pytest.raises(ValueError, match="ORPHAN_BUNDLE_ARTIFACT_REVIEW_REQUIRED"):
        run()
    assert orphan.exists()
    assert count(target, "gold.quote_bundle_stage_attempts") == 1


def test_file_fsync_precedes_link_and_no_link_fallback(setup, monkeypatch):
    _, target, root, _, run = setup
    events = []
    original = artifact_module.os.fsync

    def fsync(descriptor):
        events.append("fsync")
        return original(descriptor)

    def link(*args, **kwargs):
        events.append("link")
        raise OSError("hard links unavailable")

    monkeypatch.setattr(artifact_module.os, "fsync", fsync)
    monkeypatch.setattr(artifact_module.os, "link", link)
    with pytest.raises(OSError):
        run()
    assert events == ["fsync", "link"]
    assert not list(root.glob("*.json"))
    assert not list(root.glob(".pending-bundle-*"))
    assert count(target, "gold.quote_bundle_stages") == 0


def test_final_audit_failure_does_not_fabricate_success(setup, monkeypatch):
    _, target, root, state, run = setup
    original = AuditLedger.transition

    def transition(self, job, status, reason_code=None):
        if status == JobState.SUCCEEDED:
            raise RuntimeError("audit unavailable")
        return original(self, job, status, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", transition)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        run()
    first_job = target.execute("SELECT job_id FROM gold.quote_bundle_stage_attempts").fetchone()[0]
    assert latest(target, first_job) == "RUNNING"
    assert (root / (state["bundle"].bundle_id + ".json")).exists()
    monkeypatch.setattr(AuditLedger, "transition", original)
    second = run()
    assert second["inserted"] is False
    assert latest(target, first_job) == "RUNNING"
    assert latest(target, second["job_id"]) == "SUCCEEDED"


@pytest.mark.parametrize(
    "changes",
    [
        {"build_ids": ()},
        {"build_ids": ("bad",)},
        {"actor_id": ""},
        {"code_revision": " "},
    ],
)
def test_invalid_arguments_before_initialization(setup, changes):
    _, target, root, state, run = setup
    with pytest.raises(ValueError):
        run(**changes)
    assert count(target, "information_schema.tables") == 0
    assert not root.exists()
    assert state["calls"] == 0


def test_unsafe_root_and_legacy_target_rejected(setup, tmp_path):
    _, target, _, _, run = setup
    with pytest.raises(ValueError, match="ARTIFACT_ROOT_MUST_BE_SEPARATE_FROM_DATABASES"):
        run(artifact_root=tmp_path)
    target.execute("CREATE TABLE option_stream (id INTEGER)")
    with pytest.raises(ValueError, match="DEDICATED_BUNDLE_STAGING_DATABASE_REQUIRED"):
        run()


def test_memory_staging_rejected(setup):
    sources, _, root, state, _ = setup
    with (
        duckdb.connect(":memory:") as memory,
        pytest.raises(ValueError, match="FILE_BACKED_STAGING_DATABASE_REQUIRED"),
    ):
        service.stage_quote_bundle(
            *sources,
            memory,
            build_ids=tuple(member.build_id for member in state["bundle"].members),
            artifact_root=root,
            actor_id="test",
            code_revision="head",
            initialize=True,
        )


def test_assembly_rejection_audited_without_artifact(setup, monkeypatch):
    _, target, root, _, run = setup

    def fail(*args, **kwargs):
        raise ValueError("source not current")

    monkeypatch.setattr(service, "assemble_quote_bundle", fail)
    with pytest.raises(ValueError, match="source not current"):
        run()
    assert not root.exists()
    assert count(target, "gold.quote_bundle_stages") == 0
    assert target.execute(
        "SELECT state,reason_code FROM medallion_audit.job_events ORDER BY event_index"
    ).fetchall() == [
        ("PLANNED", None),
        ("RUNNING", None),
        ("FAILED", "EXECUTION_ERROR"),
    ]


def test_artifact_conflict_never_replaced(tmp_path):
    artifacts = BundleArtifacts(tmp_path / "artifacts")
    value = bundle()
    raw = codec.encode_quote_bundle(value)
    artifacts.write_new(raw, bundle_id=value.bundle_id)
    with pytest.raises(FileExistsError):
        artifacts.write_new(raw, bundle_id=value.bundle_id)
    assert artifacts.read_exact(value.bundle_id) == raw


def test_artifact_read_bounded_and_invalid_pin_no_io(tmp_path, monkeypatch):
    artifacts = BundleArtifacts(tmp_path / "artifacts")
    with pytest.raises(ValueError):
        artifacts.write_new(b"bad", bundle_id="f" * 64)
    assert not artifacts.root.exists()
    value = bundle()
    raw = codec.encode_quote_bundle(value)
    artifacts.write_new(raw, bundle_id=value.bundle_id)
    monkeypatch.setattr(artifact_module, "MAX_BUNDLE_BYTES", len(raw) - 2)
    with pytest.raises(ValueError):
        artifacts.read_exact(value.bundle_id)
    with pytest.raises(ValueError):
        artifacts.read_exact("../escape")


def test_source_target_alias_rejected_before_audit(setup):
    sources, target, root, state, _ = setup
    with pytest.raises(ValueError, match="SEPARATE_BUNDLE_STAGING_DATABASE_REQUIRED"):
        service.stage_quote_bundle(
            target,
            *sources[1:],
            target,
            build_ids=tuple(member.build_id for member in state["bundle"].members),
            artifact_root=root,
            actor_id="test",
            code_revision="head",
            initialize=True,
        )
    assert count(target, "information_schema.tables") == 0


def test_changed_evidence_creates_new_stage_and_preserves_old(setup):
    _, target, root, state, run = setup
    first = run()
    previous = state["bundle"]
    state["bundle"] = codec.make_quote_bundle(
        (replace(previous.members[0], evidence_fingerprint="c" * 64),)
    )
    second = run()
    assert second["bundle_id"] != first["bundle_id"]
    assert count(target, "gold.quote_bundle_stages") == 2
    assert (root / (first["bundle_id"] + ".json")).exists()
    links = target.execute(
        "SELECT supersedes_json FROM gold.quote_bundle_stages WHERE build_id=?",
        [second["bundle_id"]],
    ).fetchone()[0]
    assert json.loads(links) == [first["bundle_id"]]


def test_history_limit_checked_before_writing_new_artifact(setup, monkeypatch):
    _, target, root, state, run = setup
    monkeypatch.setattr(service, "MAX_HISTORY", 0)
    run()
    previous = state["bundle"]
    state["bundle"] = codec.make_quote_bundle(
        (replace(previous.members[0], evidence_fingerprint="c" * 64),)
    )
    with pytest.raises(ValueError, match="BUNDLE_STAGE_HISTORY_LIMIT"):
        run()
    assert not (root / (state["bundle"].bundle_id + ".json")).exists()
    assert count(target, "gold.quote_bundle_stages") == 1


def test_root_loss_does_not_silently_create_new_archive(setup):
    _, _, root, state, run = setup
    first = run()
    (root / (first["bundle_id"] + ".json")).unlink()
    root.rmdir()
    previous = state["bundle"]
    state["bundle"] = codec.make_quote_bundle(
        (replace(previous.members[0], evidence_fingerprint="c" * 64),)
    )
    with pytest.raises(ValueError, match="STAGING_ARTIFACT_ROOT_MISSING_REVIEW_REQUIRED"):
        run()
    assert not root.exists()


def test_schema_mismatch_stops_before_source_assembly(setup):
    _, target, _, state, run = setup
    run()
    target.execute("UPDATE gold.quote_bundle_stage_schema SET version=2")
    with pytest.raises(ValueError, match="STAGING_SCHEMA_OR_ROOT_BINDING_MISMATCH"):
        run()
    assert state["calls"] == 1


def test_mismatched_assembled_membership_never_writes_artifact(setup, monkeypatch):
    _, target, root, state, run = setup
    original = state["bundle"].members[0]
    data = json.loads(original.candidate_json)
    data["source_frame_revision_id"] = "f" * 64
    data["build_id"] = ""
    data["build_id"] = codec.digest(codec.canonical(data).encode())
    encoded = codec.canonical(data)
    member = replace(
        original,
        build_id=data["build_id"],
        candidate_json=encoded,
        candidate_sha256=codec.digest(encoded.encode()),
    )
    other = codec.make_quote_bundle((member,))
    monkeypatch.setattr(service, "assemble_quote_bundle", lambda *a, **kw: other)
    with pytest.raises(ValueError, match="STAGED_BUNDLE_MEMBERSHIP_MISMATCH"):
        run()
    assert not root.exists()
    assert count(target, "gold.quote_bundle_stages") == 0


def test_keyboard_interrupt_does_not_create_success(setup, monkeypatch):
    _, target, root, _, run = setup

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(service, "assemble_quote_bundle", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run()
    assert not root.exists()
    final = target.execute(
        "SELECT state,reason_code FROM medallion_audit.job_events ORDER BY event_index DESC LIMIT 1"
    ).fetchone()
    assert final == ("CANCELLED", "INTERRUPTED")


def test_bundle_version_upgrade_requires_review_before_initialization(setup, monkeypatch):
    _, target, root, _, run = setup
    monkeypatch.setattr(service, "BUNDLE_VERSION", "quote-feature-bundle@2")
    with pytest.raises(ValueError, match="UNSUPPORTED_STAGING_BUNDLE_VERSION"):
        run()
    assert count(target, "information_schema.tables") == 0
    assert not root.exists()


def test_other_gold_objects_are_not_a_dedicated_staging_database(setup):
    _, target, root, state, run = setup
    target.execute("CREATE SCHEMA gold")
    target.execute("CREATE TABLE gold.quote_price_builds (build_id VARCHAR)")
    with pytest.raises(ValueError, match="DEDICATED_BUNDLE_STAGING_DATABASE_REQUIRED"):
        run()
    assert count(target, "information_schema.tables") == 1
    assert state["calls"] == 0
    assert not root.exists()


def test_staging_catalog_named_gold_is_unambiguous(setup, tmp_path):
    sources, _, _, state, _ = setup
    root = tmp_path / "other-artifacts"
    with duckdb.connect(str(tmp_path / "gold.duckdb")) as target:
        receipt = service.stage_quote_bundle(
            *sources,
            target,
            build_ids=tuple(member.build_id for member in state["bundle"].members),
            artifact_root=root,
            actor_id="test",
            code_revision="head",
            initialize=True,
        )
        table = service._name(target, "quote_bundle_stages")
        assert target.execute(f"SELECT build_id FROM {table}").fetchone() == (receipt["bundle_id"],)


def test_missing_initialization_does_not_create_schema_or_artifact(setup):
    _, target, root, state, run = setup
    with pytest.raises(duckdb.Error):
        run(initialize=False)
    assert count(target, "information_schema.tables") == 0
    assert state["calls"] == 0
    assert not root.exists()
