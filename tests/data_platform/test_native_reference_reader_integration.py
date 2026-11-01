"""Real A1/FS1a/FS2b2/FS2b3 pipeline; local execution only, no network."""

import gzip
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform.kite_instrument_http import HttpCapture, KiteHttpCredentials
from nse_quant.data_platform.kite_instrument_http_service import acquire_instrument_reference
from nse_quant.data_platform.native_reference_decode import COLUMNS
from nse_quant.data_platform.native_reference_evidence import ReferencePins, object_name
from nse_quant.data_platform.native_reference_reader import lookup_native_reference
from nse_quant.data_platform.native_reference_silver import normalize_http_reference


@pytest.mark.parametrize("duplicates,expected", [(False, "matched"), (True, "ambiguous")])
def test_real_pipeline_to_pinned_row_evidence(tmp_path, duplicates, expected):
    path, silver_path = tmp_path / "bronze.duckdb", tmp_path / "silver.duckdb"
    row = "408065,1594,INFY,INFOSYS,0,,,0.05,1,EQ,NSE,NSE\n"
    csv = (",".join(COLUMNS) + "\n" + row + (row if duplicates else "")).encode()
    raw = gzip.compress(csv, mtime=0)
    now = datetime.now(UTC)
    capture = HttpCapture(
        "/instruments",
        now,
        now,
        now,
        now,
        200,
        (("content-encoding", "gzip"), ("content-type", "text/csv")),
        True,
        True,
        "COMPLETE",
        raw,
    )
    with duckdb.connect(str(path)) as conn:
        result = acquire_instrument_reference(
            conn,
            KiteHttpCredentials("fixture-key", "fixture-token"),
            capture_session_id="reader-fixture",
            actor_id="test",
            code_revision="fixture",
            initialize=True,
            fetcher=lambda *args, **kwargs: capture,
        )
    pins = ReferencePins(
        result.body_capture_event_id,
        result.body_envelope_hash,
        result.metadata_capture_event_id,
        result.metadata_envelope_hash,
    )
    bronze = duckdb.connect(str(path), read_only=True)
    try:
        with duckdb.connect(str(silver_path)) as silver:
            normalized = normalize_http_reference(
                bronze, silver, pins=pins, actor_id="test", code_revision="fixture", initialize=True
            )
            assert normalized["classification"] == "normalized"
    finally:
        bronze.close()
    bronze = duckdb.connect(str(path), read_only=True)
    silver = duckdb.connect(str(silver_path), read_only=True)
    try:
        table = object_name(silver, "silver", "kite_http_reference_results")
        before = silver.execute(f"SELECT * FROM {table}").fetchall()
        revision = normalized["revision_id"]
        assert isinstance(revision, str)
        lookup = lookup_native_reference(
            bronze, silver, assessment_revision_id=revision, instrument_token=408065
        )
        assert lookup.status == expected
        assert len(lookup.candidates) == (2 if duplicates else 1)
        assert all(c.assessment_revision_id == revision for c in lookup.candidates)
        assert not lookup.publication_asserted and not lookup.historical_validity_asserted
        assert silver.execute(f"SELECT * FROM {table}").fetchall() == before
    finally:
        silver.close()
        bronze.close()
