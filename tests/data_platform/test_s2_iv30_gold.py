"""Audited Gold candidate persistence/retrieval; no publication or decision authority."""

import json
from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from nse_quant.data_platform import s2_iv30_gold as api

REVISION = "a" * 64
MATERIALIZATION = "b" * 64
SILVER_REVISION = "c" * 64
AS_OF = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
CODE_REVISION = "1" * 40


def feature_bytes(**changes):
    now = datetime.now(UTC)
    source_time = now - timedelta(seconds=5)
    feature = {
        "version": api.FEATURE_VERSION,
        "feature_kind": "live_iv30_observation",
        "as_of": now.isoformat(),
        "iv30": 0.15,
        "source_time": source_time.isoformat(),
        "received_at": (source_time + timedelta(seconds=1)).isoformat(),
        "age_seconds": 5.0,
        "max_age_seconds": 300.0,
        "value_percent": 15.0,
        "selected_revision_id": "d" * 64,
        "source_revisions": ["d" * 64],
        "instrument_token": 123,
        "raw_payload_sha256": "e" * 64,
        "instrument_reference_sha256": "f" * 64,
        "iv30_source": "india_vix",
        "mode": "observation",
        "quality_state": "valid_observation",
        "publication_asserted": False,
        "decision_eligibility_asserted": False,
        "model_suitability_verified": False,
        "vrp_gate_passed": False,
        "provenance": {
            "observation_id": REVISION,
            "materialization_sha256": MATERIALIZATION,
            "revision_id": SILVER_REVISION,
            "materialization_available_at": (source_time + timedelta(seconds=2)).isoformat(),
        },
    }
    feature.update(changes)
    if "iv30" in changes and "value_percent" not in changes:
        feature["value_percent"] = float(changes["iv30"]) * 100
    return json.dumps(feature, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@pytest.fixture
def stores(tmp_path, monkeypatch):
    paths = [tmp_path / f"{name}.duckdb" for name in ("bronze", "silver", "materialization", "gold")]
    for path in paths:
        with duckdb.connect(str(path)):
            pass
    sources = [duckdb.connect(str(path), read_only=True) for path in paths[:3]]
    gold = duckdb.connect(str(paths[3]))
    current = {"raw": feature_bytes()}

    def read_live(*args, **kwargs):
        assert args == (sources[2], sources[0], sources[1])
        assert kwargs["observation_id"] == REVISION
        assert kwargs["expected_sha256"] == MATERIALIZATION
        return current["raw"]

    monkeypatch.setattr(api.feature_reader, "read_live_feature", read_live)

    def persist(**changes):
        values = {
            "observation_id": REVISION,
            "expected_sha256": MATERIALIZATION,
            "as_of": AS_OF,
            "actor_id": "test-suite",
            "code_revision": CODE_REVISION,
            "initialize_store": True,
        }
        values.update(changes)
        return api.persist_live_candidate(*sources, gold, **values)

    yield sources, gold, paths[3], current, persist
    for conn in [*sources, gold]:
        conn.close()


def test_persists_audited_candidate_without_publication(stores):
    _, gold, _, current, persist = stores
    receipt = persist()
    assert receipt["status"] == "candidate"
    assert receipt["published"] is False
    assert receipt["decision_eligibility_asserted"] is False
    row = gold.execute(
        'SELECT status,reason_code,published_at,feature_sha256 FROM "gold"."gold".s2_iv30_candidates'
    ).fetchone()
    assert row[:3] == ("candidate", "OBSERVATIONAL_IV30_CANDIDATE", None)
    assert row[3] == api.sha(current["raw"])
    assert gold.execute(
        "SELECT state FROM medallion_audit.job_events WHERE job_id=? ORDER BY event_index DESC LIMIT 1",
        [receipt["job_id"]],
    ).fetchone() == ("SUCCEEDED",)


def test_exact_retry_reuses_immutable_candidate_but_audits_attempt(stores):
    _, gold, _, _, persist = stores
    first = persist()
    second = persist(initialize_store=False)
    assert first["build_id"] == second["build_id"]
    assert first["input_revision_id"] == second["input_revision_id"]
    assert second["inserted"] is False
    assert first["job_id"] != second["job_id"]
    assert gold.execute('SELECT COUNT(*) FROM "gold"."gold".s2_iv30_candidates').fetchone()[0] == 1
    assert gold.execute("SELECT COUNT(*) FROM medallion_audit.job_events WHERE state='SUCCEEDED'").fetchone()[0] == 2
    assert gold.execute('SELECT COUNT(*) FROM "gold"."gold".s2_iv30_candidate_attempts').fetchone()[0] == 2


def test_feature_change_creates_new_candidate_revision(stores):
    _, gold, _, current, persist = stores
    first = persist()
    current["raw"] = feature_bytes(iv30=0.16)
    second = persist(initialize_store=False)
    assert first["build_id"] != second["build_id"]
    assert gold.execute('SELECT COUNT(*) FROM "gold"."gold".s2_iv30_candidates').fetchone()[0] == 2


def test_retrieval_requires_exact_pin_asof_and_successful_audit(stores):
    _, gold, path, _, persist = stores
    receipt = persist()
    gold.close()
    with duckdb.connect(str(path), read_only=True) as reader:
        result = api.retrieve_candidate(reader, build_id=receipt["build_id"], as_of=AS_OF)
    assert result["status"] == "CANDIDATE_RETRIEVED_NOT_PUBLISHED"
    assert result["feature"]["iv30"] == pytest.approx(0.15)
    assert result["published_at"] is None
    assert result["publication_asserted"] is False
    assert result["decision_eligibility_asserted"] is False
    assert result["model_suitability_verified"] is False


def test_candidate_not_available_before_recording_or_event_time(stores):
    _, gold, path, current, persist = stores
    receipt = persist()
    before_event = datetime.fromisoformat(json.loads(current["raw"])["source_time"]) - timedelta(seconds=1)
    gold.close()
    with duckdb.connect(str(path), read_only=True) as reader, pytest.raises(ValueError, match="NOT_YET_AVAILABLE"):
        api.retrieve_candidate(
            reader,
            build_id=receipt["build_id"],
            as_of=before_event.isoformat(),
        )


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"iv30_source": "internal_cm"}, "PROFILE_OR_AUTHORITY"),
        ({"publication_asserted": True}, "PROFILE_OR_AUTHORITY"),
        ({"decision_eligibility_asserted": True}, "PROFILE_OR_AUTHORITY"),
        ({"model_suitability_verified": True}, "PROFILE_OR_AUTHORITY"),
        ({"vrp_gate_passed": True}, "PROFILE_OR_AUTHORITY"),
        ({"iv30": -0.01}, "FINITE_POSITIVE_IV30"),
        (
            {"source_time": (datetime.fromisoformat(AS_OF) + timedelta(seconds=1)).isoformat()},
            "FUTURE_OR_UNORDERED_FEATURE_DEPENDENCY",
        ),
    ],
)
def test_invalid_feature_candidate_rejected_before_gold_write(stores, changes, reason):
    _, gold, _, current, persist = stores
    current["raw"] = feature_bytes(**changes)
    with pytest.raises(ValueError, match=reason):
        persist()
    assert gold.execute("SELECT COUNT(*) FROM information_schema.tables").fetchone()[0] == 0


def test_duplicate_source_database_rejected(stores):
    sources, gold, _, _, _ = stores
    with pytest.raises(ValueError, match="SEPARATE_READONLY_SOURCES"):
        api.persist_live_candidate(
            sources[0],
            sources[0],
            sources[2],
            gold,
            observation_id=REVISION,
            expected_sha256=MATERIALIZATION,
            as_of=AS_OF,
            actor_id="test",
            code_revision=CODE_REVISION,
        )
    assert gold.execute("SELECT COUNT(*) FROM information_schema.tables").fetchone()[0] == 0


def test_feature_must_match_both_requested_source_pins(stores):
    _, gold, _, current, persist = stores
    altered = json.loads(feature_bytes())
    altered["provenance"]["materialization_sha256"] = "9" * 64
    current["raw"] = json.dumps(altered, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    with pytest.raises(ValueError, match="OBSERVATION_OR_MATERIALIZATION_PIN_MISMATCH"):
        persist()
    assert gold.execute("SELECT COUNT(*) FROM information_schema.tables").fetchone()[0] == 0


def test_retrieval_recomputes_candidate_identity_from_feature(stores):
    _, gold, path, _, persist = stores
    receipt = persist()
    gold.execute(
        'UPDATE "gold"."gold".s2_iv30_candidates SET input_revision_id=? WHERE build_id=?',
        ["9" * 64, receipt["build_id"]],
    )
    gold.close()
    with (
        duckdb.connect(str(path), read_only=True) as reader,
        pytest.raises(ValueError, match="CANDIDATE_CONTRACT_MISMATCH"),
    ):
        api.retrieve_candidate(reader, build_id=receipt["build_id"], as_of=AS_OF)


def test_definition_tampering_is_not_repaired(stores):
    _, gold, _, _, persist = stores
    persist()
    gold.execute('UPDATE "gold"."gold".s2_iv30_candidate_definitions SET definition=? ', [b"[]"])
    with pytest.raises(ValueError, match="DEFINITION_DRIFT"):
        persist(initialize_store=False)
    assert gold.execute('SELECT definition FROM "gold"."gold".s2_iv30_candidate_definitions').fetchone() == (b"[]",)


def test_unexpected_gold_table_blocks_reuse(stores):
    _, gold, _, _, persist = stores
    persist()
    gold.execute('CREATE TABLE "gold"."gold".unexpected_artifact (value INTEGER)')
    with pytest.raises(ValueError, match="STORE_INVENTORY_MISMATCH"):
        persist(initialize_store=False)


def test_feature_tampering_blocks_retrieval(stores):
    _, gold, path, _, persist = stores
    receipt = persist()
    gold.execute(
        'UPDATE "gold"."gold".s2_iv30_candidates SET feature_json=? WHERE build_id=?',
        [b"{}", receipt["build_id"]],
    )
    gold.close()
    with duckdb.connect(str(path), read_only=True) as reader, pytest.raises(ValueError, match="HASH_MISMATCH"):
        api.retrieve_candidate(reader, build_id=receipt["build_id"], as_of=AS_OF)


def test_failed_original_audit_is_not_accepted_or_healed(stores, monkeypatch):
    _, gold, path, _, persist = stores
    original = api.AuditLedger.transition

    def fail_success(self, job_id, state, reason_code=None):
        if state.value == "SUCCEEDED":
            raise RuntimeError("simulated final audit failure")
        return original(self, job_id, state, reason_code)

    monkeypatch.setattr(api.AuditLedger, "transition", fail_success)
    with pytest.raises(RuntimeError, match="final audit failure"):
        persist()
    build_id = gold.execute('SELECT build_id FROM "gold"."gold".s2_iv30_candidates').fetchone()[0]
    job_id = gold.execute('SELECT first_job_id FROM "gold"."gold".s2_iv30_candidates').fetchone()[0]
    assert gold.execute(
        "SELECT state FROM medallion_audit.job_events WHERE job_id=? ORDER BY event_index DESC LIMIT 1",
        [job_id],
    ).fetchone() == ("RUNNING",)
    monkeypatch.setattr(api.AuditLedger, "transition", original)
    retry = persist(initialize_store=False)
    assert retry["inserted"] is False
    gold.close()
    with (
        duckdb.connect(str(path), read_only=True) as reader,
        pytest.raises(ValueError, match="AUDIT_ATTEMPT_NOT_TERMINAL"),
    ):
        api.retrieve_candidate(
            reader,
            build_id=build_id,
            as_of=AS_OF,
        )
