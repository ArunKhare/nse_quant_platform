"""Actual synthetic native window producer -> bundle/publication/read/admission paths."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import duckdb
import pytest
from test_legacy_candle_returns_native import build as build_returns
from test_legacy_candle_returns_native import returns_target as returns_target
from test_legacy_market_gold_native import build as build_geometry
from test_legacy_market_gold_native import native as native
from test_legacy_market_gold_native import pipeline as pipeline
from test_legacy_market_partition_silver_native import bronze_target as bronze_target
from test_legacy_market_partition_silver_native import legacy as legacy
from test_legacy_market_partitions_native import build as preserve
from test_legacy_return_window_native import build as build_window
from test_legacy_return_window_native import window_target as window_target

from nse_quant.data_platform import legacy_market_gold as gold_codec
from nse_quant.data_platform import legacy_market_partition_silver as silver_codec
from nse_quant.data_platform import legacy_market_partition_silver_store as silver_store
from nse_quant.data_platform import legacy_window_admission as admission
from nse_quant.data_platform import legacy_window_publication as service
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.publication_admission import (
    ARCHIVED_RESEARCH,
    POINT_IN_TIME,
    AdmissionRequest,
)


def assemble(target, request):
    returns_target = target[0]
    native = returns_target[0]
    with (
        duckdb.connect(str(native[0][1]), read_only=True) as bronze,
        duckdb.connect(str(native[0][2]), read_only=True) as silver,
        duckdb.connect(str(native[1]), read_only=True) as geometry,
        duckdb.connect(str(returns_target[1]), read_only=True) as returns,
        duckdb.connect(str(target[1]), read_only=True) as windows,
    ):
        return service.bundle.assemble_window_bundle(
            bronze, silver, geometry, returns, windows, request=request
        )


@pytest.fixture
def publication_target(window_target, tmp_path):
    result = build_window(window_target)
    request = service.bundle.WindowBundleRequest(
        result["build_id"], result["recording_fingerprint"]
    )
    raw = assemble(window_target, request)
    directory = tmp_path / "window_publication"
    directory.mkdir()
    path = directory / "gold.duckdb"  # Real catalog/schema collision preserved.
    with duckdb.connect(str(path)) as c:
        service.initialize_window_publication(c)
    return window_target, path, request, service.bundle.sha(raw)


def publish(target, **changes):
    window_target, path, request, reviewed = target
    returns_target = window_target[0]
    native = returns_target[0]
    args = dict(
        request=request,
        expected_bundle_id=reviewed,
        actor_id="synthetic",
        code_revision="a" * 40,
        purpose=service.PURPOSE,
        allow_research_publication=True,
    )
    args.update(changes)
    with (
        duckdb.connect(str(native[0][1]), read_only=True) as bronze,
        duckdb.connect(str(native[0][2]), read_only=True) as silver,
        duckdb.connect(str(native[1]), read_only=True) as geometry,
        duckdb.connect(str(returns_target[1]), read_only=True) as returns,
        duckdb.connect(str(window_target[1]), read_only=True) as windows,
        duckdb.connect(str(path)) as output,
    ):
        return service.publish_window_research_bundle(
            bronze, silver, geometry, returns, windows, output, **args
        )


def read(target, result, current=False):
    wt, path, _request, _reviewed = target
    rt, native = wt[0], wt[0][0]
    args = dict(
        publication_id=result["publication_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(path), read_only=True) as output:
        if not current:
            return service.read_window_publication(output, **args)
        with (
            duckdb.connect(str(native[0][1]), read_only=True) as bronze,
            duckdb.connect(str(native[0][2]), read_only=True) as silver,
            duckdb.connect(str(native[1]), read_only=True) as geometry,
            duckdb.connect(str(rt[1]), read_only=True) as returns,
            duckdb.connect(str(wt[1]), read_only=True) as windows,
        ):
            return service.revalidate_window_publication(
                bronze, silver, geometry, returns, windows, output, **args
            )


def test_complete_actual_chain_full_publication_coverage_and_policy(publication_target):
    result = publish(publication_target)
    retained = read(publication_target, result)
    assert retained == read(publication_target, result, current=True)
    assert retained.row_count == 1001
    doc = json.loads(retained.manifest_bytes)
    assert len(doc["inputs"]) == len(doc["outputs"]) == 1001
    outputs = [json.loads(bytes.fromhex(r)) for r in doc["outputs"]]
    assert [r["source_ordinal"] for r in outputs] == list(range(1001))
    assert {r["partition_index"] for r in outputs} == {0, 1}
    assert doc["policy"] == dict(window_returns=2, cadence_microseconds=60000000)
    assert retained.research_publication_verified
    assert not retained.decision_eligibility_asserted
    assert not retained.authoritative_market_coverage_verified
    assert doc["publication_asserted"] is False
    with duckdb.connect(str(publication_target[1]), read_only=True) as c:
        table = service.name(c, "medallion_audit", "job_events")
        assert c.execute(f"SELECT state FROM {table} ORDER BY event_index").fetchall() == [
            (s,) for s in ("PLANNED", "RUNNING", "STAGED", "VALIDATED", "PUBLISHED", "SUCCEEDED")
        ]


def test_actual_archival_admission_and_point_in_time_refusal(publication_target):
    result = publish(publication_target)
    at = datetime.now(UTC)
    with duckdb.connect(str(publication_target[1]), read_only=True) as c:
        args = dict(
            publication_id=result["publication_id"],
            expected_recording_fingerprint=result["recording_fingerprint"],
        )
        research = admission.assess_window_publication_use(
            c, **args, request=AdmissionRequest(ARCHIVED_RESEARCH)
        )
        decision = admission.assess_window_publication_use(
            c, **args, request=AdmissionRequest(POINT_IN_TIME, at, at)
        )
    assert research.policy_status == "ACCEPTED_RESEARCH_ONLY"
    assert research.research_analysis_permitted
    assert decision.policy_status == "REJECTED"
    assert not decision.research_analysis_permitted
    for receipt in (research, decision):
        assert not receipt.decision_eligibility_asserted
        assert not receipt.research_analysis_authorized
        raw = admission.encode_window_admission(receipt)
        assert (
            admission.replay_window_admission(raw, expected_receipt_id=receipt.receipt_id)
            == receipt
        )


@pytest.mark.parametrize(
    "case",
    ["drop-input", "drop-output", "reverse", "policy", "flag"],
    ids=["input", "output", "order", "policy", "eligibility"],
)
def test_rehashed_offline_bundle_corruption_not_accepted(publication_target, case):
    raw = assemble(publication_target[0], publication_target[2])
    doc = json.loads(raw)
    if case == "drop-input":
        doc["inputs"].pop()
    elif case == "drop-output":
        doc["outputs"].pop()
    elif case == "reverse":
        doc["outputs"].reverse()
    elif case == "policy":
        doc["policy"]["window_returns"] = 3
    else:
        doc["decision_eligibility_asserted"] = True
    changed = service.bundle.canonical(doc)
    with pytest.raises(ValueError):
        service.bundle.replay_window_bundle(changed, expected_bundle_id=service.bundle.sha(changed))


def test_offline_recording_declaration_is_not_native_source_attestation(publication_target):
    doc = json.loads(assemble(publication_target[0], publication_target[2]))
    doc["request"]["recording_fingerprint"] = "0" * 64
    changed = service.bundle.canonical(doc)
    assert (
        service.bundle.replay_window_bundle(changed, expected_bundle_id=service.bundle.sha(changed))
        == changed
    )
    request = service.bundle.WindowBundleRequest(**doc["request"])
    with pytest.raises(ValueError):
        assemble(publication_target[0], request)


@pytest.mark.parametrize(
    "column,value",
    [
        ("row_count", "1"),
        ("manifest_bytes", "'bad'::BLOB"),
        ("manifest_byte_count", "1"),
        ("purpose", "'POINT_IN_TIME_DECISION'"),
        ("feature_version", "'bad'"),
        ("event_ts", "current_timestamp"),
        ("effective_from", "current_timestamp"),
        ("decision_eligibility_asserted", "true"),
        ("first_job_id", "'bad'"),
    ],
    ids=["rows", "bytes", "length", "purpose", "version", "event", "from", "decision", "origin"],
)
def test_materialized_scalar_and_content_corruption(publication_target, column, value):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as c:
        c.execute(f"UPDATE {service.name(c, 'gold', service.DOMAIN[1])} SET {column}={value}")
    with pytest.raises(ValueError):
        read(publication_target, result)


@pytest.mark.parametrize(
    "case",
    ["link", "audit", "contract", "definition", "policy"],
    ids=["link", "audit", "contract", "definition", "policy"],
)
def test_original_recording_obligations(publication_target, case):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as c:
        if case == "link":
            c.execute(f"DELETE FROM {service.name(c, 'gold', service.DOMAIN[2])}")
        elif case == "audit":
            table = service.name(c, "medallion_audit", "job_events")
            c.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
        elif case == "contract":
            table = service.name(c, "medallion_audit", "dataset_contracts")
            c.execute(f"UPDATE {table} SET fingerprint='bad'")
        elif case == "definition":
            table = service.name(c, "gold", service.DOMAIN[0])
            c.execute(f"UPDATE {table} SET definition='bad'::BLOB")
        else:
            table = service.name(c, "gold", service.DOMAIN[1])
            c.execute(
                f"UPDATE {table} SET policy_bytes=?",
                [service.bundle.canonical(dict(window_returns=3, cadence_microseconds=60000000))],
            )
    with pytest.raises(ValueError):
        read(publication_target, result)


def test_changed_review_pin_cannot_heal_original_scope(publication_target):
    with pytest.raises(ValueError):
        publish(publication_target, expected_bundle_id="0" * 64)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


def test_changed_source_recording_pin_cannot_heal_scope(publication_target):
    request = replace(publication_target[2], recording_fingerprint="0" * 64)
    with pytest.raises(ValueError):
        publish(publication_target, request=request)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


def test_extra_scoped_failure_is_not_good_subset(publication_target):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as c:
        ledger = AuditLedger(c)
        job = ledger.plan_job(
            command_name=service.COMMAND,
            actor_id="synthetic",
            code_revision="a" * 40,
            config_hash="b" * 64,
            scope_ref="sha256:" + service.scope_id(publication_target[2].build_id),
        )
        ledger.transition(job, JobState.FAILED, "EXECUTION_ERROR")
    with pytest.raises(ValueError):
        read(publication_target, result)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


@pytest.mark.parametrize("phase", ["PUBLISHED", "SUCCEEDED"], ids=["published", "final-success"])
def test_post_domain_audit_failure_no_adoption(publication_target, monkeypatch, phase):
    original = AuditLedger.transition

    def fail(self, job, state, reason_code=None):
        if state == JobState(phase):
            raise RuntimeError("SYNTHETIC_POST_DOMAIN_AUDIT")
        return original(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail)
    with pytest.raises(RuntimeError, match="POST_DOMAIN"):
        publish(publication_target)
    monkeypatch.setattr(AuditLedger, "transition", original)
    key = service.publication_id(publication_target[2].build_id, publication_target[3])
    with pytest.raises(ValueError, match="AUDIT"):
        read(publication_target, dict(publication_id=key, recording_fingerprint="a" * 64))
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


def test_actual_sql_domain_rollback(publication_target):
    with duckdb.connect(str(publication_target[1])) as c:
        table = service.name(c, "gold", service.DOMAIN[2])
        c.execute(f"ALTER TABLE {table} ADD COLUMN synthetic_failure INTEGER DEFAULT 0")
    with pytest.raises(duckdb.Error):
        publish(publication_target)
    with duckdb.connect(str(publication_target[1]), read_only=True) as c:
        for n in service.DOMAIN[1:]:
            table = service.name(c, "gold", n)
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


@pytest.mark.parametrize(
    "column,size,code",
    [
        ("manifest_bytes", 140000001, "AGGREGATE_BYTE_BOUND"),
        ("request_bytes", 513, "COMPONENT_BOUND"),
        ("policy_bytes", 513, "COMPONENT_BOUND"),
    ],
    ids=["manifest-total", "request-cell", "policy-cell"],
)
def test_independent_sql_transfer_bounds(publication_target, column, size, code):
    result = publish(publication_target)
    with duckdb.connect(str(publication_target[1])) as c:
        table = service.name(c, "gold", service.DOMAIN[1])
        c.execute(f"UPDATE {table} SET {column}=encode(repeat('x',?))", [size])
    with pytest.raises(ValueError, match=code):
        read(publication_target, result)


def test_retained_publication_current_window_and_legacy_sql_distinct(publication_target):
    result = publish(publication_target)
    wt = publication_target[0]
    native = wt[0][0]
    with duckdb.connect(str(native[0][0])) as c:
        c.execute(f"UPDATE {service.name(c, 'main', 'spot_candles')} SET close=7")
    assert read(publication_target, result, current=True).row_count == 1001
    with duckdb.connect(str(wt[1])) as c:
        table = service.name(c, "medallion_audit", "job_events")
        c.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    assert read(publication_target, result).row_count == 1001
    with pytest.raises(ValueError):
        read(publication_target, result, current=True)


def test_first_write_before_actual_assembler(publication_target, monkeypatch):
    publish(publication_target)

    def forbidden(*args, **kwargs):
        raise AssertionError("upstream must not be called")

    monkeypatch.setattr(service.bundle, "assemble_window_bundle", forbidden)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


def test_timezone_readonly_and_no_reinitialization(publication_target):
    result = publish(publication_target)
    args = dict(
        publication_id=result["publication_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(publication_target[1]), read_only=True) as c:
        c.execute("SET TimeZone='Asia/Kolkata'")
        assert service.read_window_publication(c, **args).row_count == 1001
    with duckdb.connect(str(publication_target[1])) as c:
        with pytest.raises(ValueError, match="READONLY"):
            service.read_window_publication(c, **args)
        with pytest.raises(ValueError, match="EMPTY"):
            service.initialize_window_publication(c)


def test_actual_computed_series_through_native_publication(legacy, bronze_target, tmp_path):
    with duckdb.connect(str(legacy)) as c:
        table = service.name(c, "main", "spot_candles")
        c.execute(f"DELETE FROM {table}")
        at = datetime(2026, 1, 1, tzinfo=UTC)
        for i, price in enumerate([1.0, 2.0, 4.0, 8.0]):
            c.execute(
                f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?)",
                [1, "S", "1m", at + timedelta(minutes=i), None, None, None, price, 0, None],
            )
    br = preserve(legacy, bronze_target)
    bp = silver_codec.PartitionBronzePins(
        br["capture_id"], "spot_candles", "synthetic", br["recording_fingerprint"]
    )
    sp, gp, rp, wp, pp = (
        tmp_path / f"{n}.duckdb"
        for n in (
            "series_silver",
            "series_geometry",
            "series_returns",
            "series_windows",
            "series_publication",
        )
    )
    source = service.bundle.source
    with (
        duckdb.connect(str(bronze_target), read_only=True) as bronze,
        duckdb.connect(str(sp)) as silver,
    ):
        silver_store.initialize_partition_silver(silver)
        sr = silver_store.persist_partition_silver(
            bronze, silver, pins=bp, actor_id="synthetic", code_revision="a" * 40
        )
    with duckdb.connect(str(gp)) as geometry:
        source.source.source.initialize_legacy_price_gold(geometry)
    original = (
        (legacy, bronze_target, sp, bp),
        gp,
        gold_codec.GoldSourcePins(sr["revision_id"], sr["recording_fingerprint"]),
    )
    gr = build_geometry(original)
    with duckdb.connect(str(rp)) as returns:
        source.source.initialize_candle_return_gold(returns)
    rt = original, rp, source.source.CandleReturnPins(gr["build_id"], gr["recording_fingerprint"])
    rr = build_returns(rt)
    with duckdb.connect(str(wp)) as windows:
        source.initialize_return_window_gold(windows)
    wt = (
        rt,
        wp,
        source.ReturnWindowPins(rr["build_id"], rr["recording_fingerprint"]),
        source.features.ReturnWindowPolicy(2, 60000000),
    )
    wr = build_window(wt)
    request = service.bundle.WindowBundleRequest(wr["build_id"], wr["recording_fingerprint"])
    raw = assemble(wt, request)
    with duckdb.connect(str(pp)) as publications:
        service.initialize_window_publication(publications)
    target = wt, pp, request, service.bundle.sha(raw)
    result = publish(target)
    retained = read(target, result, current=True)
    doc = json.loads(retained.manifest_bytes)
    rows = [json.loads(bytes.fromhex(r)) for r in doc["outputs"]]
    assert len(rows) == 4
    assert rows[0]["values"]["status"] == rows[1]["values"]["status"] == "UNAVAILABLE"
    assert rows[2]["values"]["sum_squared_simple_returns"] == dict(numerator="2", denominator="1")
    assert rows[3]["values"]["mean_squared_simple_returns"] == dict(numerator="1", denominator="1")
    assert not rows[3]["values"]["authoritative_market_coverage_verified"]


def test_second_actual_assembly_failure_no_domain_adoption(publication_target, monkeypatch):
    original = service.bundle.assemble_window_bundle
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_WINDOW_ASSEMBLY")
        return original(*args, **kwargs)

    monkeypatch.setattr(service.bundle, "assemble_window_bundle", observe)
    with pytest.raises(RuntimeError, match="SECOND_WINDOW_ASSEMBLY"):
        publish(publication_target)
    with duckdb.connect(str(publication_target[1]), read_only=True) as c:
        for n in service.DOMAIN[1:]:
            table = service.name(c, "gold", n)
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


def test_incomplete_original_window_cannot_publish_subset(publication_target):
    source = service.bundle.source
    with duckdb.connect(str(publication_target[0][1])) as c:
        table = source.name(c, "gold", source.DOMAIN[3])
        c.execute(f"DELETE FROM {table} WHERE ordinal=1000")
    with pytest.raises(ValueError):
        publish(publication_target)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        publish(publication_target)


def test_same_live_file_alias_preserves_parent(publication_target):
    with duckdb.connect(str(publication_target[1])) as c:
        alias = c.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                service.publish_window_research_bundle(
                    c,
                    None,
                    None,
                    None,
                    None,
                    alias,
                    request=publication_target[2],
                    expected_bundle_id=publication_target[3],
                    actor_id="synthetic",
                    code_revision="a" * 40,
                    purpose=service.PURPOSE,
                    allow_research_publication=True,
                )
            assert c.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()


def test_orphan_attempt_blocks_before_source(publication_target, monkeypatch):
    with duckdb.connect(str(publication_target[1])) as c:
        table = service.name(c, "gold", service.DOMAIN[2])
        c.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?)",
            [
                "orphan",
                service.scope_id(publication_target[2].build_id),
                publication_target[2].build_id,
                "a" * 64,
            ],
        )

    def forbidden(*args, **kwargs):
        raise AssertionError("orphan must refuse before source")

    monkeypatch.setattr(service.bundle, "assemble_window_bundle", forbidden)
    with pytest.raises(ValueError, match="ORPHAN"):
        publish(publication_target)


def test_bundle_input_count_preflight_before_hex_decode(publication_target):
    doc = json.loads(assemble(publication_target[0], publication_target[2]))
    doc["inputs"] = ["00"] * 16001
    raw = service.bundle.canonical(doc)
    with pytest.raises(ValueError, match="COUNT_BOUND"):
        service.bundle.replay_window_bundle(raw, expected_bundle_id=service.bundle.sha(raw))
