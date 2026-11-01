"""Real CSV parser and DuckDB projection; native lookup boundary substituted, NOT E2E."""

import csv
import io
from dataclasses import asdict, replace

import duckdb
import pytest

from nse_quant.data_platform import native_derivative_description as service
from nse_quant.data_platform.native_reference_decode import COLUMNS, canonical, parse_native_csv
from nse_quant.data_platform.native_reference_reader import (
    NativeReferenceLookup,
    NativeReferenceRowPin,
)
from nse_quant.data_platform.reference_supersession import RESOLVER_VERSION


def quote(value):
    return '"' + value.replace('"', '""') + '"'


@pytest.fixture(params=["silver", "odd'catalog\"name"])
def pinned(tmp_path, request, monkeypatch):
    bronze = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    silver = duckdb.connect(":memory:")
    path = str(tmp_path / "reference.duckdb").replace("'", "''")
    silver.execute(f"ATTACH '{path}' AS {quote(request.param)}")
    silver.execute(f"USE {quote(request.param)}")
    silver.execute("CREATE SCHEMA silver")
    table = ".".join(map(quote, (request.param, "silver", "kite_http_reference_results")))
    silver.execute(f"CREATE TABLE {table}(revision_id VARCHAR,result_json VARCHAR)")
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(COLUMNS)
    writer.writerow(
        [
            "257",
            "1",
            "NOT_PARSED",
            "NIFTY",
            "100.00",
            "2026-11-24",
            "25000.00",
            "0.05",
            "1",
            "CE",
            "NFO-OPT",
            "NFO",
        ]
    )
    parsed = parse_native_csv(text.getvalue().encode())
    assert parsed.classification == "normalized"
    silver.execute(f"INSERT INTO {table} VALUES (?,?)", ["a" * 64, canonical(asdict(parsed))])
    pin = NativeReferenceRowPin("a" * 64, 0, parsed.rows[0].source_fields_hash)
    state = {
        "value": NativeReferenceLookup(
            RESOLVER_VERSION,
            "a" * 64,
            257,
            "matched",
            "UNIQUE_TOKEN_ROW",
            ("a" * 64,),
            (pin,),
        ),
        "calls": 0,
    }

    def lookup(*args, **kwargs):
        state["calls"] += 1
        return state["value"]

    monkeypatch.setattr(service, "lookup_native_reference", lookup)

    def run():
        return service.read_native_derivative_description(
            bronze,
            silver,
            assessment_revision_id="a" * 64,
            instrument_token=257,
        )

    yield silver, table, state, run
    bronze.close()
    silver.close()


def test_projection_uses_actual_typed_native_csv_fields(pinned):
    silver, table, state, run = pinned
    before = silver.execute(f"SELECT * FROM {table}").fetchall()
    value = run()
    assert value.status == "described"
    assert value.native_reference_lookup_verified
    assert value.description.normalized_strike == "25000"
    assert not value.description.provenance_verified
    assert not value.canonical_identity_asserted
    assert not value.historical_validity_asserted
    assert not value.decision_eligibility_asserted
    assert state["calls"] == 2
    assert silver.execute(f"SELECT * FROM {table}").fetchall() == before


@pytest.mark.parametrize("status", ["blocked", "ambiguous", "unresolved"])
def test_lookup_rejection_never_supplies_description(pinned, status):
    _, _, state, run = pinned
    state["value"] = replace(state["value"], status=status)
    value = run()
    assert value.status == "blocked"
    assert value.description is None
    assert state["calls"] == 1


def test_projected_source_hash_mismatch_blocks(pinned):
    _, _, state, run = pinned
    state["value"] = replace(
        state["value"], candidates=(NativeReferenceRowPin("a" * 64, 0, "f" * 64),)
    )
    assert run().reason_codes == ("NATIVE_REFERENCE_PROJECTED_PIN_MISMATCH",)


def test_drift_on_second_lookup_blocks(pinned, monkeypatch):
    _, _, state, run = pinned
    calls = 0

    def lookup(*args, **kwargs):
        nonlocal calls
        calls += 1
        return state["value"] if calls == 1 else replace(state["value"], status="blocked")

    monkeypatch.setattr(service, "lookup_native_reference", lookup)
    value = run()
    assert value.reason_codes == ("NATIVE_REFERENCE_OBSERVATION_DRIFT",)
    assert value.description is None


def test_sql_failure_is_not_fabricated_business_outcome(pinned):
    silver, table, _, run = pinned
    silver.execute(f"DROP TABLE {table}")
    with pytest.raises(duckdb.Error):
        run()


def test_projection_size_limit_blocks(pinned, monkeypatch):
    _, _, _, run = pinned
    monkeypatch.setattr(service, "MAX_ROW_BYTES", 1)
    value = run()
    assert value.description is None
    assert value.reason_codes == ("NATIVE_REFERENCE_ROW_PROJECTION_LIMIT_OR_MISSING",)
