"""Native VIX Bronze/Silver -> retained bars, temporary files only.

Supplied for checkout execution; not included in the isolated EOD validation.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from nse_quant.data_platform import india_vix_recording as vix
from nse_quant.data_platform import s2_series_materialization as api
from nse_quant.market_data.india_vix_inputs import RawVixCapture

AT = datetime(2026, 11, 20, 5, tzinfo=UTC)
REVISION = "a" * 40
OBSERVATION = "b" * 64


def native_case(tmp_path, *, price=15.0):
    bp, sp, target = (tmp_path / name for name in ("bronze.duckdb", "vix.duckdb", "series.duckdb"))
    pins = []
    reference = json.dumps(dict(exchange="NSE", segment="INDICES", tradingsymbol="INDIA VIX", instrument_token=123))
    with duckdb.connect(str(bp)) as bronze:
        vix.initialize_vix_bronze(bronze, writer_owner="fixture")
        for index, seconds in enumerate((10, 20, 130)):
            stamp = AT + timedelta(seconds=seconds)
            payload = json.dumps(
                {"NSE:INDIA VIX": dict(instrument_token=123, last_price=price, timestamp=stamp.isoformat())}
            )
            capture = RawVixCapture(
                "NSE:INDIA VIX",
                123,
                hashlib.sha256(reference.encode()).hexdigest(),
                reference,
                stamp,
                stamp,
                payload,
                hashlib.sha256(payload.encode()).hexdigest(),
            )
            receipt = vix.preserve_vix_capture(
                bronze,
                capture,
                capture_session_id="fixture",
                source_record_id=f"request-{index}",
                writer_owner="fixture",
                code_revision=REVISION,
            )
            assert not receipt["conflicted"]
            pins.append((receipt["pins"], stamp))
    revisions = []
    with duckdb.connect(str(bp), read_only=True) as bronze, duckdb.connect(str(sp)) as silver:
        vix.initialize_vix_silver(silver, writer_owner="fixture")
        for pin, stamp in pins:
            context, _ = vix.observe_vix_bronze(bronze, pins=pin, as_of=stamp)
            receipt = vix.persist_vix_silver(
                bronze,
                silver,
                pins=pin,
                as_of=stamp,
                expected_context_sha256=api.sha(context),
                writer_owner="fixture",
                code_revision=REVISION,
            )
            revisions.append(receipt["revision_id"])
    with duckdb.connect(str(target)) as writer:
        api.initialize(writer, actor_id="fixture", code_revision=REVISION)
    return bp, sp, target, revisions


def prepare_and_persist(case):
    bp, sp, target, revisions = case
    with duckdb.connect(str(bp), read_only=True) as bronze, duckdb.connect(str(sp), read_only=True) as silver:
        raw = api.prepare_minutes(bronze, silver, revision_ids=revisions)
        with duckdb.connect(str(target)) as writer:
            receipt = api.persist(
                writer,
                raw=raw,
                observation_id=OBSERVATION,
                expected_sha256=api.sha(raw),
                actor_id="fixture",
                code_revision=REVISION,
                bronze=bronze,
                vix_silver=silver,
            )
    return raw, receipt


def test_native_bronze_silver_minute_materialization_and_readonly_replay(tmp_path):
    case = native_case(tmp_path)
    raw, receipt = prepare_and_persist(case)
    assert not receipt["conflicted"]
    bp, sp, target, _ = case
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (bp, sp, target)]
    with (
        duckdb.connect(str(bp), read_only=True) as bronze,
        duckdb.connect(str(sp), read_only=True) as silver,
        duckdb.connect(str(target), read_only=True) as reader,
    ):
        replayed = api.replay(
            reader,
            kind=api.MINUTE,
            observation_id=OBSERVATION,
            expected_sha256=api.sha(raw),
            bronze=bronze,
            vix_silver=silver,
        )
    assert replayed == raw
    bars = json.loads(raw)["content"]["bars"]
    assert len(bars) == 2 and bars[0]["sample_count"] == 2
    assert bars[0]["close"] == pytest.approx(0.15)
    assert before == [hashlib.sha256(path.read_bytes()).hexdigest() for path in (bp, sp, target)]


def test_native_silver_tampering_invalidates_retained_minute_replay(tmp_path):
    case = native_case(tmp_path)
    raw, _ = prepare_and_persist(case)
    bp, sp, target, _ = case
    with duckdb.connect(str(sp)) as writer:
        writer.execute("UPDATE silver.india_vix_records SET record_bytes='bad'::BLOB")
    with (
        duckdb.connect(str(bp), read_only=True) as bronze,
        duckdb.connect(str(sp), read_only=True) as silver,
        duckdb.connect(str(target), read_only=True) as reader,
        pytest.raises((ValueError, KeyError, TypeError)),
    ):
        api.replay(
            reader,
            kind=api.MINUTE,
            observation_id=OBSERVATION,
            expected_sha256=api.sha(raw),
            bronze=bronze,
            vix_silver=silver,
        )


def test_rejected_native_revision_is_not_materialized_as_a_bar(tmp_path):
    bp, sp, target, revisions = native_case(tmp_path, price=-1.0)
    with (
        duckdb.connect(str(bp), read_only=True) as bronze,
        duckdb.connect(str(sp), read_only=True) as silver,
        pytest.raises(ValueError, match="REJECTED"),
    ):
        api.prepare_minutes(bronze, silver, revision_ids=revisions)
    with duckdb.connect(str(target), read_only=True) as reader:
        assert reader.execute("SELECT count(*) FROM silver.s2_series_materializations").fetchone() == (0,)
