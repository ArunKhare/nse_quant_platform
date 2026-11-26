"""Native S2 surface recording: Bronze-linked capture, audit and exact replay."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pytest

from nse_quant.analytics import constant_maturity_inputs as cm
from nse_quant.data_platform import india_vix_recording as common
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform import native_option_chain_snapshot as codec
from nse_quant.data_platform import native_option_chain_snapshot_bronze as bronze_api
from nse_quant.data_platform import native_surface_recording as surface
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore

REVISION = "a" * 40
IST = ZoneInfo("Asia/Kolkata")
AS_OF = datetime(2026, 11, 24, 9, 15, tzinfo=IST)


def _source_fixture(tmp_path: Path) -> tuple[Path, list[dict[str, str]], dict[str, tuple[bytes, str]], dict[str, Any]]:
    bronze_path = tmp_path / "option_bronze.duckdb"
    pins: list[dict[str, str]] = []
    expiries: list[datetime] = []

    with duckdb.connect(str(bronze_path)) as writer:
        AuditLedger(writer).initialize()
        BronzeEventStore(writer).initialize()
        for days in (25, 40, 80, 100):
            expiry_date = AS_OF.date() + timedelta(days=days)
            expiry_close = datetime.combine(expiry_date, time(15, 30), IST)
            expiries.append(expiry_close)
            quotes = []
            for option_type in ("CE", "PE"):
                for strike in (22000.0, 23500.0, 25000.0, 26500.0, 28000.0):
                    premium = cm.black76_price(
                        25000.0,
                        strike,
                        (expiry_close.astimezone(UTC) - AS_OF.astimezone(UTC)).total_seconds() / cm.YEAR_SECONDS,
                        0.05,
                        0.25,
                        option_type,
                    )
                    token = len(quotes) + 1 + (days * 10)
                    quotes.append(
                        dict(
                            instrument=dict(
                                tradingsymbol=f"NIFTY-{days}-{option_type}-{strike:g}",
                                instrument_token=token,
                                underlying="NIFTY",
                                expiry=expiry_date.isoformat(),
                                strike=strike,
                                option_type=option_type,
                                lot_size=75,
                            ),
                            ltp=float(premium),
                            bid=float(premium),
                            ask=float(premium),
                            volume=1000,
                            oi=500,
                            exchange_ts=AS_OF.isoformat(),
                            trade_ts=AS_OF.isoformat(),
                            received_at=AS_OF.isoformat(),
                        )
                    )
            document = dict(
                ts=AS_OF.isoformat(),
                underlying="NIFTY",
                spot=25000.0,
                expiry=expiry_date.isoformat(),
                is_market_open=True,
                quotes=quotes,
            )
            source_label = f"synthetic-expiry-{days}"
            payload = codec.make_snapshot(source_label, document)
            receipt = bronze_api.preserve_option_chain_snapshot(
                writer,
                source_label=source_label,
                payload=payload,
                expected_snapshot_id=codec.snapshot_id(payload),
                imported_at=AS_OF.astimezone(UTC),
                actor_id="surface-test",
                code_revision=REVISION,
                origin_kind="historical_import",
            )
            pins.append(
                dict(
                    source_label=receipt["source_label"],
                    snapshot_id=receipt["snapshot_id"],
                    capture_event_id=receipt["capture_event_id"],
                    envelope_hash=receipt["envelope_hash"],
                    expected_recording_fingerprint=receipt["recording_fingerprint"],
                )
            )

    closes = [value.isoformat() for value in expiries]
    calendar = dict(source="synthetic-reviewed-calendar", available_at=AS_OF.isoformat(), closes=closes)
    forwards = [
        dict(
            expiry_close=close,
            kind="matched_forward_observation",
            evidence=dict(
                underlying="NIFTY",
                forward=25000.0,
                source="synthetic-forward-source",
                source_time=AS_OF.isoformat(),
                received_at=AS_OF.isoformat(),
            ),
        )
        for close in closes
    ]
    rates = {
        close: dict(
            annual_rate=0.05,
            convention="annual_continuously_compounded",
            source="synthetic-rate-source",
            available_at=AS_OF.isoformat(),
        )
        for close in closes
    }
    artifacts = {}
    for kind, data in (("calendar", calendar), ("forward", forwards), ("rate", rates)):
        raw = common.canonical(dict(kind=kind, data=data))
        artifacts[kind] = (raw, surface.bundle.sha256(raw))
    policy = dict(
        as_of=AS_OF.isoformat(),
        max_age_seconds=300,
        max_source_gap_seconds=30,
        kernel=cm.VERSION,
        delta=cm.DELTA_CONVENTION,
    )
    return bronze_path, pins, artifacts, policy


@pytest.fixture
def surface_case(tmp_path: Path):
    bronze_path, pins, artifacts, policy = _source_fixture(tmp_path)
    target_path = tmp_path / "surface_silver.duckdb"
    with duckdb.connect(str(target_path)) as writer:
        surface.initialize(writer, actor_id="surface-test", code_revision=REVISION)
    return bronze_path, target_path, pins, artifacts, policy


def _record(bronze_path, target_path, pins, artifacts, policy, observation_id="b" * 64):
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(target_path)) as target,
    ):
        expected = surface.assemble(bronze, snapshots=pins, artifacts=artifacts, policy=policy)
        return surface.persist(
            bronze,
            target,
            observation_id=observation_id,
            expected_sha256=surface.bundle.sha256(expected),
            actor_id="surface-test",
            code_revision=REVISION,
            snapshots=pins,
            artifacts=artifacts,
            policy=policy,
        ), expected


def test_native_surface_recording_and_readonly_replay(surface_case):
    bronze_path, target_path, pins, artifacts, policy = surface_case
    receipt, expected = _record(bronze_path, target_path, pins, artifacts, policy)
    assert receipt == dict(conflicted=False, exact_retry=False, decision_eligibility_asserted=False)

    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(target_path), read_only=True) as reader,
    ):
        result = surface.replay(
            bronze,
            reader,
            observation_id="b" * 64,
            expected_sha256=surface.bundle.sha256(expected),
        )
    assert result["iv30"]["iv"] == pytest.approx(0.25)
    assert result["iv90"]["iv"] == pytest.approx(0.25)
    assert result["rr25"] == pytest.approx(0.0)
    assert result["decision_eligibility_asserted"] is False


def test_native_surface_exact_retry_is_idempotent(surface_case):
    bronze_path, target_path, pins, artifacts, policy = surface_case
    first, expected = _record(bronze_path, target_path, pins, artifacts, policy)
    second, _ = _record(bronze_path, target_path, pins, artifacts, policy)
    assert first["exact_retry"] is False
    assert second == dict(conflicted=False, exact_retry=True, decision_eligibility_asserted=False)

    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(target_path), read_only=True) as reader,
    ):
        surface.replay(
            bronze,
            reader,
            observation_id="b" * 64,
            expected_sha256=surface.bundle.sha256(expected),
        )


def test_native_surface_changed_evidence_quarantines_observation_id(surface_case):
    bronze_path, target_path, pins, artifacts, policy = surface_case
    _, expected = _record(bronze_path, target_path, pins, artifacts, policy)
    changed_policy = dict(policy, max_age_seconds=301)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(target_path)) as target,
    ):
        changed = surface.assemble(bronze, snapshots=pins, artifacts=artifacts, policy=changed_policy)
        receipt = surface.persist(
            bronze,
            target,
            observation_id="b" * 64,
            expected_sha256=surface.bundle.sha256(changed),
            actor_id="surface-test",
            code_revision=REVISION,
            snapshots=pins,
            artifacts=artifacts,
            policy=changed_policy,
        )
    assert receipt["conflicted"] is True
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(target_path), read_only=True) as reader,
        pytest.raises(ValueError, match="MISSING_CONFLICTED_OR_WRONG_PIN"),
    ):
        surface.replay(
            bronze,
            reader,
            observation_id="b" * 64,
            expected_sha256=surface.bundle.sha256(expected),
        )


def test_native_surface_rejects_changed_artifact_pin(surface_case):
    bronze_path, target_path, pins, artifacts, policy = surface_case
    changed = dict(artifacts)
    raw, _pin = changed["calendar"]
    changed["calendar"] = (raw + b" ", surface.bundle.sha256(raw))
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        pytest.raises(ValueError, match="ARTIFACT_PIN_OR_BOUND_MISMATCH"),
    ):
        surface.assemble(bronze, snapshots=pins, artifacts=changed, policy=policy)


def test_native_surface_replay_requires_successful_original_audit(surface_case):
    bronze_path, target_path, pins, artifacts, policy = surface_case
    _, expected = _record(bronze_path, target_path, pins, artifacts, policy)
    with duckdb.connect(str(target_path)) as writer:
        writer.execute(
            """
            UPDATE medallion_audit.job_events
            SET state='FAILED', reason_code='EXECUTION_ERROR'
            WHERE job_id=(SELECT job_id FROM silver.s2_surface_variants)
              AND event_index=3
            """
        )
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(target_path), read_only=True) as reader,
        pytest.raises(ValueError, match="SUCCESSFUL_ORIGINAL_AUDIT_REQUIRED"),
    ):
        surface.replay(
            bronze,
            reader,
            observation_id="b" * 64,
            expected_sha256=surface.bundle.sha256(expected),
        )
