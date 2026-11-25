"""Real temporary native Bronze and DuckDB journal; never operational files."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from nse_quant.analytics import constant_maturity_inputs as cm
from nse_quant.data_platform import india_vix_recording as common
from nse_quant.data_platform import native_option_chain_snapshot as codec
from nse_quant.data_platform import native_option_chain_snapshot_bronze as bronze_api
from nse_quant.data_platform import s2_observation_journal as api
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore

AT = datetime(2026, 11, 24, 10, tzinfo=UTC)
REV = "a" * 40
SCOPE = "b" * 64


@pytest.fixture
def case(tmp_path):
    path, target = tmp_path / "bronze.duckdb", tmp_path / "surface.duckdb"
    snapshots, closes, forwards, rates = [], [], [], {}
    with duckdb.connect(str(path)) as conn:
        AuditLedger(conn).initialize()
        BronzeEventStore(conn).initialize()
        token = 0
        for days in (20, 40, 80, 100):
            close = AT + timedelta(days=days)
            expiry = close.date().isoformat()
            closes.append(close.isoformat())
            quotes = []
            for kind in ("CE", "PE"):
                for strike in (85.0, 95.0, 100.0, 105.0, 115.0):
                    token += 1
                    sigma = 0.2 if kind == "CE" else 0.24
                    price = cm.black76_price(100, strike, days / 365, 0.05, sigma, kind)
                    quotes.append(
                        dict(
                            instrument=dict(
                                tradingsymbol=f"TEST-{token}",
                                instrument_token=token,
                                underlying="NIFTY",
                                expiry=expiry,
                                strike=strike,
                                option_type=kind,
                                lot_size=75,
                            ),
                            ltp=price,
                            bid=price,
                            ask=price,
                            volume=1,
                            oi=1,
                            exchange_ts=AT.isoformat(),
                            trade_ts=AT.isoformat(),
                            received_at=AT.isoformat(),
                        )
                    )
            label = f"s2-synthetic-{days}"
            raw = codec.make_snapshot(
                label,
                dict(
                    ts=AT.isoformat(),
                    underlying="NIFTY",
                    spot=100.0,
                    expiry=expiry,
                    is_market_open=True,
                    quotes=quotes,
                ),
            )
            receipt = bronze_api.preserve_option_chain_snapshot(
                conn,
                source_label=label,
                payload=raw,
                expected_snapshot_id=codec.snapshot_id(raw),
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REV,
                origin_kind="historical_import",
            )
            snapshots.append(
                {
                    k: receipt[k]
                    for k in (
                        "source_label",
                        "snapshot_id",
                        "capture_event_id",
                        "envelope_hash",
                    )
                }
                | {"expected_recording_fingerprint": receipt["recording_fingerprint"]}
            )
            forwards.append(
                dict(
                    expiry_close=close.isoformat(),
                    kind="matched_forward_observation",
                    evidence=dict(
                        underlying="NIFTY",
                        forward=100,
                        source="synthetic-forward",
                        source_time=AT.isoformat(),
                        received_at=AT.isoformat(),
                    ),
                )
            )
            rates[close.isoformat()] = dict(
                annual_rate=0.05,
                convention="annual_continuously_compounded",
                source="synthetic-rate",
                available_at=AT.isoformat(),
            )

    def request(*, stale=False, rate=0.05):
        r = deepcopy(rates)
        for value in r.values():
            value["annual_rate"] = rate
        artifacts = {}
        for kind, data in dict(
            calendar=dict(source="synthetic-calendar", available_at=AT.isoformat(), closes=closes),
            forward=forwards,
            rate=r,
        ).items():
            raw = common.canonical(dict(kind=kind, data=data))
            artifacts[kind] = raw, api.base.sha(raw)
        policy = dict(
            as_of=(AT + timedelta(seconds=301) if stale else AT).isoformat(),
            max_age_seconds=300,
            max_source_gap_seconds=30,
            kernel=cm.VERSION,
            delta=cm.DELTA_CONVENTION,
        )
        return api.request_bytes(snapshots=snapshots, artifacts=artifacts, policy=policy)

    with duckdb.connect(str(target)) as conn:
        api.initialize(conn, actor_id="synthetic", code_revision=REV)
    return path, target, request


def persist(case, request):
    bronze_path, target_path, _ = case
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(target_path)) as target,
    ):
        body = api.observe(bronze, request)
        receipt = api.persist(
            bronze,
            target,
            request=request,
            observation_id=SCOPE,
            expected_sha256=api.base.sha(body),
            actor_id="synthetic",
            code_revision=REV,
        )
    return body, receipt


def test_valid_native_bronze_persist_retry_and_readonly_replay(case):
    body, receipt = persist(case, case[2]())
    _, retry = persist(case, case[2]())
    assert retry["exact_retry"] and not receipt["conflicted"]
    with (
        duckdb.connect(str(case[0]), read_only=True) as bronze,
        duckdb.connect(str(case[1]), read_only=True) as reader,
    ):
        value = api.replay(bronze, reader, observation_id=SCOPE, expected_sha256=api.base.sha(body))
    result = value["record"]["bundle"]["result"]
    assert result["rr25"] == pytest.approx(-0.04, abs=1e-8)
    assert value["quality_state"] == "valid_observation"
    assert value["decision_eligibility_asserted"] is False


def test_rejected_input_is_durably_replayable(case):
    body, receipt = persist(case, case[2](stale=True))
    assert receipt["quality_state"] == "rejected"
    with (
        duckdb.connect(str(case[0]), read_only=True) as bronze,
        duckdb.connect(str(case[1]), read_only=True) as reader,
    ):
        value = api.replay(bronze, reader, observation_id=SCOPE, expected_sha256=api.base.sha(body))
    assert value["quality_state"] == "rejected" and value["record"] is None
    assert value["request"]["artifacts"]


def test_competing_variants_retained_and_replay_blocked(case):
    body, _ = persist(case, case[2]())
    _, changed = persist(case, case[2](rate=0.04))
    assert changed["conflicted"]
    with (
        duckdb.connect(str(case[0]), read_only=True) as bronze,
        duckdb.connect(str(case[1]), read_only=True) as reader,
    ):
        with pytest.raises(ValueError, match="CONFLICTED"):
            api.replay(bronze, reader, observation_id=SCOPE, expected_sha256=api.base.sha(body))
        assert reader.execute(f"SELECT count(*) FROM {api.TABLE}").fetchone() == (2,)


def test_review_pin_mismatch_creates_no_domain_or_audit_rows(case):
    with (
        duckdb.connect(str(case[0]), read_only=True) as bronze,
        duckdb.connect(str(case[1])) as target,
    ):
        with pytest.raises(ValueError, match="REVIEWED"):
            api.persist(
                bronze,
                target,
                request=case[2](),
                observation_id=SCOPE,
                expected_sha256="c" * 64,
                actor_id="synthetic",
                code_revision=REV,
            )
        assert target.execute(f"SELECT count(*) FROM {api.TABLE}").fetchone() == (0,)
        assert target.execute("SELECT count(*) FROM medallion_audit.jobs").fetchone() == (0,)


def test_orphan_job_blocks_recording_without_healing(case):
    with (
        duckdb.connect(str(case[0]), read_only=True) as bronze,
        duckdb.connect(str(case[1])) as target,
    ):
        AuditLedger(target).plan_job(
            command_name=api.COMMAND,
            actor_id="synthetic",
            code_revision=REV,
            scope_ref=SCOPE,
            config_hash="c" * 64,
        )
        with pytest.raises(ValueError, match="ORPHAN"):
            api.persist(
                bronze,
                target,
                request=case[2](),
                observation_id=SCOPE,
                expected_sha256="c" * 64,
                actor_id="synthetic",
                code_revision=REV,
            )
        assert target.execute(f"SELECT count(*) FROM {api.TABLE}").fetchone() == (0,)


def test_body_tampering_blocks_retry(case):
    persist(case, case[2]())
    with duckdb.connect(str(case[1])) as writer:
        writer.execute(f"UPDATE {api.TABLE} SET body='bad'::BLOB")
    with pytest.raises(ValueError, match="INTEGRITY"):
        persist(case, case[2]())


def test_unverified_bronze_is_not_archived_as_quality_rejection(case):
    doc = json.loads(case[2]())
    doc["snapshots"][0]["expected_recording_fingerprint"] = "0" * 64
    with (
        duckdb.connect(str(case[0]), read_only=True) as bronze,
        pytest.raises(ValueError),
    ):
        api.observe(bronze, common.canonical(doc))


def test_insert_failure_rolls_back_and_retains_failed_audit(case, monkeypatch):
    original = api._insert

    def failing(*args):
        original(*args)
        raise RuntimeError("synthetic failure after insert")

    monkeypatch.setattr(api, "_insert", failing)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        persist(case, case[2]())
    with duckdb.connect(str(case[1]), read_only=True) as reader:
        assert reader.execute(f"SELECT count(*) FROM {api.TABLE}").fetchone() == (0,)
        states = reader.execute("SELECT state FROM medallion_audit.job_events ORDER BY event_index").fetchall()
        assert states == [("PLANNED",), ("RUNNING",), ("FAILED",)]


def test_missing_final_audit_blocks_replay(case):
    body, _ = persist(case, case[2]())
    with duckdb.connect(str(case[1])) as writer:
        writer.execute("DELETE FROM medallion_audit.job_events WHERE state='SUCCEEDED'")
    with (
        duckdb.connect(str(case[0]), read_only=True) as bronze,
        duckdb.connect(str(case[1]), read_only=True) as reader,
        pytest.raises(ValueError, match="SUCCESSFUL_ORIGINAL_AUDIT"),
    ):
        api.replay(bronze, reader, observation_id=SCOPE, expected_sha256=api.base.sha(body))
