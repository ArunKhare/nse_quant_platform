"""End-to-end replay and preregistration tests for the NIFTY IV30 proxy study."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pytest
import test_india_vix_recording as vix_fixture
import test_native_surface_recording as surface_fixture

from nse_quant.data_platform import native_surface_recording as surface
from nse_quant.research import india_vix_iv30_proxy_study as study

IST = ZoneInfo("Asia/Kolkata")
OWNER = "proxy-study-test"
REVISION = "b" * 40


def _condition(now: datetime, tags: list[str]) -> bytes:
    value = dict(
        source="reviewed-market-condition-fixture",
        trade_date=now.astimezone(IST).date().isoformat(),
        as_of=now.isoformat(),
        available_at=(now - timedelta(seconds=1)).isoformat(),
        tags=tags,
    )
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


@pytest.fixture
def stores(tmp_path: Path, monkeypatch):
    now = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(vix_fixture, "NOW", now)
    monkeypatch.setattr(surface_fixture, "AS_OF", now.astimezone(IST))

    vix_bronze_path = tmp_path / "vix_bronze.duckdb"
    vix_silver_path = tmp_path / "vix_silver.duckdb"
    vix_pins = vix_fixture.preserve(vix_bronze_path, vix_fixture.capture())
    vix_revision = vix_fixture.promote(vix_bronze_path, vix_silver_path, vix_pins["pins"])["revision_id"]

    option_bronze_path, snapshots, artifacts, surface_policy = surface_fixture._source_fixture(tmp_path)
    surface_silver_path = tmp_path / "surface_silver.duckdb"
    with duckdb.connect(str(surface_silver_path)) as writer:
        surface.initialize(writer, actor_id=OWNER, code_revision=REVISION)
    with duckdb.connect(str(option_bronze_path), read_only=True) as bronze:
        expected = surface.assemble(bronze, snapshots=snapshots, artifacts=artifacts, policy=surface_policy)
        surface_digest = surface.bundle.sha256(expected)
        with duckdb.connect(str(surface_silver_path)) as writer:
            surface.persist(
                bronze,
                writer,
                observation_id="c" * 64,
                expected_sha256=surface_digest,
                actor_id=OWNER,
                code_revision=REVISION,
                snapshots=snapshots,
                artifacts=artifacts,
                policy=surface_policy,
            )

    with (
        duckdb.connect(str(vix_silver_path), read_only=True) as vix_reader,
        duckdb.connect(str(surface_silver_path), read_only=True) as surface_reader,
    ):
        vix_available, _ = study._vix_available_at(vix_reader, vix_revision)
        surface_available, _ = study._surface_available_at(surface_reader, "c" * 64, surface_digest)
    condition = _condition(max(vix_available, surface_available), ["NORMAL"])
    request = study.ProxyPairRequest(
        vix_silver_revision_id=vix_revision,
        surface_observation_id="c" * 64,
        surface_sha256=surface_digest,
        condition_artifact=condition,
        condition_sha256=hashlib.sha256(condition).hexdigest(),
    )
    return (
        vix_bronze_path,
        vix_silver_path,
        option_bronze_path,
        surface_silver_path,
        request,
        now,
        tmp_path / "proxy_study.duckdb",
    )


def _policy() -> study.ProxyAcceptancePolicy:
    return study.ProxyAcceptancePolicy(
        max_abs_bias=0.02,
        max_mae=0.02,
        max_rmse=0.03,
        max_p90_absolute_error=0.05,
        min_correlation=0.0,
        min_ols_slope=0.5,
        max_ols_slope=1.5,
    )


def test_pair_replays_exact_vix_and_surface_sources(stores):
    bp, sp, op, vp, request, now, _journal = stores
    with (
        duckdb.connect(str(bp), read_only=True) as vix_bronze,
        duckdb.connect(str(sp), read_only=True) as vix_silver,
        duckdb.connect(str(op), read_only=True) as option_bronze,
        duckdb.connect(str(vp), read_only=True) as surface_silver,
    ):
        pair = study.replay_matched_pair(vix_bronze, vix_silver, option_bronze, surface_silver, request)
    assert pair.underlying == "NIFTY"
    assert pair.surface_iv_source == "internal_cm"
    assert pair.condition_tags == ("NORMAL",)
    assert pair.condition_evidence_sha256 == request.condition_sha256
    assert pair.condition_evidence_json == request.condition_artifact.decode()
    assert pair.vix_available_at is not None and pair.surface_available_at is not None
    assert pair.as_of >= pair.vix_available_at
    assert pair.as_of >= pair.surface_available_at
    assert pair.as_of >= now


def test_policy_is_preregistered_before_immutable_pairset_and_report(stores):
    bp, sp, op, vp, request, _now, journal = stores
    with duckdb.connect(str(journal)) as writer:
        study.initialize_study_store(writer, actor_id=OWNER, code_revision=REVISION)
        policy_id = study.register_acceptance_policy(writer, _policy(), actor_id=OWNER, code_revision=REVISION)
        with (
            duckdb.connect(str(bp), read_only=True) as vix_bronze,
            duckdb.connect(str(sp), read_only=True) as vix_silver,
            duckdb.connect(str(op), read_only=True) as option_bronze,
            duckdb.connect(str(vp), read_only=True) as surface_silver,
        ):
            pair_set_id = study.persist_pair_set(
                vix_bronze,
                vix_silver,
                option_bronze,
                surface_silver,
                writer,
                requests=[request],
                policy_id=policy_id,
                actor_id=OWNER,
                code_revision=REVISION,
            )
        report = study.persist_evaluation_report(writer, pair_set_id, actor_id=OWNER, code_revision=REVISION)
        report_sha256 = study.evaluation_report_sha256(report)
    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["suitability_asserted"] is False
    assert report["decision_eligibility_asserted"] is False
    assert report["publication_asserted"] is False
    assert report["pair_source_replay_verified_at_pairset_creation"] is True
    assert report["pair_source_availability_verified_at_pairset_creation"] is True
    assert report["atomic_cross_database_snapshot_asserted"] is False
    assert report["preregistered_policy_id"] == policy_id
    assert set(report["condition_results"]) == set(study.CONDITIONS)
    assert report["condition_results"]["EVENT"]["status"] == "INSUFFICIENT_HOLDOUT_EVIDENCE"
    with (
        duckdb.connect(str(bp), read_only=True) as vix_bronze,
        duckdb.connect(str(sp), read_only=True) as vix_silver,
        duckdb.connect(str(op), read_only=True) as option_bronze,
        duckdb.connect(str(vp), read_only=True) as surface_silver,
        duckdb.connect(str(journal), read_only=True) as reader,
    ):
        reproduced = study.replay_pair_set(vix_bronze, vix_silver, option_bronze, surface_silver, reader, pair_set_id)
        replayed_report = study.replay_evaluation_report(
            reader,
            pair_set_id,
            report_sha256,
            actor_id=OWNER,
            code_revision=REVISION,
        )
    assert len(reproduced) == 1
    assert replayed_report == report


def test_pair_rejects_invalid_condition_artifact_pin(stores):
    bp, sp, op, vp, request, _now, _journal = stores
    changed = study.ProxyPairRequest(
        request.vix_silver_revision_id,
        request.surface_observation_id,
        request.surface_sha256,
        request.condition_artifact + b" ",
        request.condition_sha256,
    )
    with (
        duckdb.connect(str(bp), read_only=True) as vix_bronze,
        duckdb.connect(str(sp), read_only=True) as vix_silver,
        duckdb.connect(str(op), read_only=True) as option_bronze,
        duckdb.connect(str(vp), read_only=True) as surface_silver,
        pytest.raises(ValueError, match="CONDITION_ARTIFACT_PIN_OR_BOUND_MISMATCH"),
    ):
        study.replay_matched_pair(vix_bronze, vix_silver, option_bronze, surface_silver, changed)


def test_pairset_requires_preregistered_policy(stores):
    bp, sp, op, vp, request, _now, journal = stores
    with (
        duckdb.connect(str(journal)) as writer,
        duckdb.connect(str(bp), read_only=True) as vix_bronze,
        duckdb.connect(str(sp), read_only=True) as vix_silver,
        duckdb.connect(str(op), read_only=True) as option_bronze,
        duckdb.connect(str(vp), read_only=True) as surface_silver,
    ):
        study.initialize_study_store(writer, actor_id=OWNER, code_revision=REVISION)
        with pytest.raises(ValueError, match="PREREGISTERED_POLICY_NOT_FOUND"):
            study.persist_pair_set(
                vix_bronze,
                vix_silver,
                option_bronze,
                surface_silver,
                writer,
                requests=[request],
                policy_id="d" * 64,
                actor_id=OWNER,
                code_revision=REVISION,
            )


def test_policy_cannot_omit_required_market_conditions() -> None:
    policy = study.ProxyAcceptancePolicy(
        max_abs_bias=0.02,
        max_mae=0.02,
        max_rmse=0.03,
        max_p90_absolute_error=0.05,
        min_correlation=0.0,
        min_ols_slope=0.5,
        max_ols_slope=1.5,
        required_conditions=("NORMAL",),
    )
    with pytest.raises(ValueError, match="INVALID_PROXY_ACCEPTANCE_POLICY"):
        policy.validate()
