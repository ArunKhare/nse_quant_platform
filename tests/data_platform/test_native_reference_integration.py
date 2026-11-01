"""Real committed A1/FS1a/FS2b2 integration, supplied for local execution only."""

import gzip
import json

import duckdb
import pytest

from nse_quant.data_platform.kite_instrument_http import HttpCapture, KiteHttpCredentials
from nse_quant.data_platform.kite_instrument_http_service import (
    HttpAcquisitionRejected,
    acquire_instrument_reference,
)
from nse_quant.data_platform.native_reference_decode import COLUMNS
from nse_quant.data_platform.native_reference_evidence import ReferencePins, object_name
from nse_quant.data_platform.native_reference_silver import normalize_http_reference


def acquire_fixture(path, *, malformed_gzip=False, rejected=False):
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    csv = (",".join(COLUMNS) + "\n408065,1594,INFY,INFOSYS,0,,,0.05,1,EQ,NSE,NSE\n").encode()
    body = gzip.compress(csv, mtime=0)
    if malformed_gzip:
        body = body[:-2]
    capture = HttpCapture(
        "/instruments",
        now,
        now,
        now,
        now,
        403 if rejected else 200,
        (("content-encoding", "gzip"), ("content-type", "text/csv")),
        True,
        True,
        "COMPLETE",
        body,
    )
    with duckdb.connect(str(path)) as conn:
        try:
            result = acquire_instrument_reference(
                conn,
                KiteHttpCredentials("fixture-key", "fixture-token"),
                capture_session_id="integration-fixture",
                actor_id="test",
                code_revision="fixture",
                initialize=True,
                fetcher=lambda *args, **kwargs: capture,
            )
        except HttpAcquisitionRejected as error:
            if not rejected:
                raise
            result = error.result
    return ReferencePins(
        result.body_capture_event_id,
        result.body_envelope_hash,
        result.metadata_capture_event_id,
        result.metadata_envelope_hash,
    )


@pytest.mark.parametrize(
    "malformed,rejected,classification,reason",
    [
        (False, False, "normalized", "NORMALIZED"),
        (True, False, "quarantine", "TRUNCATED_GZIP"),
        (False, True, "quarantine", "ACQUISITION_NOT_SUCCEEDED"),
    ],
)
def test_real_native_pipeline(tmp_path, malformed, rejected, classification, reason):
    bronze_path, silver_path = tmp_path / "bronze.duckdb", tmp_path / "silver.duckdb"
    pins = acquire_fixture(bronze_path, malformed_gzip=malformed, rejected=rejected)
    bronze = duckdb.connect(str(bronze_path), read_only=True)
    silver = duckdb.connect(str(silver_path))
    try:
        source = object_name(bronze, "bronze", "event_variants")
        before = bronze.execute(f"SELECT * FROM {source} ORDER BY ingest_sequence").fetchall()
        args = dict(pins=pins, actor_id="test", code_revision="fixture", initialize=True)
        first = normalize_http_reference(bronze, silver, **args)
        second = normalize_http_reference(bronze, silver, **args)
        assert first["classification"] == classification and first["reason_code"] == reason
        assert first["revision_id"] == second["revision_id"] and not second["inserted"]
        target = object_name(silver, "silver", "kite_http_reference_results")
        row = silver.execute(f"SELECT * FROM {target}").fetchone()
        assert row is not None, "Expected a persisted native reference assessment"

        assert row[17:21] == (None, None, None, None)
        data = json.loads(row[24])
        if classification == "normalized":
            assert data["rows"][0]["strike_decimal"] is None
        else:
            assert data["rows"] == []
        assert silver.execute(f"SELECT count(*) FROM {target}").fetchone() == (1,)
        after = bronze.execute(f"SELECT * FROM {source} ORDER BY ingest_sequence").fetchall()
        assert after == before
    finally:
        silver.close()
        bronze.close()
