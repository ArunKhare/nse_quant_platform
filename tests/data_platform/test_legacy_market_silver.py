"""Pure Silver projection and real disposable SQL scalar-materialization checks."""

import json
from copy import deepcopy

import duckdb
import pytest

from nse_quant.data_platform import legacy_market_silver as codec


def observations(table="spot_candles"):
    names = codec.CANDLE_NAMES if table == "spot_candles" else codec.OPTION_NAMES
    fields = dict.fromkeys(names)
    fields.update(instrument_token="257", ts="2026-01-01T00:00:00+00:00", volume="0", oi=None)
    if table == "spot_candles":
        fields.update(interval="1m", symbol="SYNTHETIC", open=(-0.0).hex(), close=(1.0).hex())
    else:
        fields.update(run_id="synthetic", iv=(0.2).hex(), strike=(100.0).hex())
    return (
        dict(
            snapshot_id="c" * 64,
            ordinal=0,
            table=table,
            stored_fields=fields,
            legacy_derived_fields={k: v for k, v in fields.items() if k in codec.DERIVED},
            source_time_semantics="LEGACY_STORED_TS_NOT_INDEPENDENT_AVAILABILITY",
            original_provider_bytes_retained=False,
            identity_verified=False,
            availability_evidence_verified=False,
            decision_eligibility_asserted=False,
        ),
    )


def pins():
    return codec.LegacyBronzePins("a" * 64, "b" * 64, "c" * 64)


@pytest.mark.parametrize("table", ["spot_candles", "option_stream"])
def test_complete_projection_and_sql_materialization(tmp_path, table):
    rows = codec.derive_records(observations(table), pins=pins())
    doc = json.loads(rows[0])
    assert doc["decision_eligibility_asserted"] is False
    assert doc["canonical_contract_id"] is None
    assert doc["stored_fields"]["oi"] is None
    assert doc["stored_fields"]["volume"] == "0"
    if table == "option_stream":
        assert doc["legacy_derived_fields"]["iv"] == (0.2).hex()
    else:
        assert doc["stored_fields"]["open"] == (-0.0).hex()
    values = codec.record_values(rows[0])
    with duckdb.connect(str(tmp_path / "materialized.duckdb")) as conn:
        conn.execute(
            "CREATE TABLE materialized (id VARCHAR,ordinal INTEGER,source_table VARCHAR,"
            "token BIGINT,ts TIMESTAMPTZ,volume BIGINT,oi BIGINT,raw BLOB)"
        )
        conn.execute("INSERT INTO materialized VALUES (?,?,?,?,?,?,?,?)", list(values))
        conn.execute("SET TimeZone='Asia/Kolkata'")
        assert conn.execute("SELECT * FROM materialized").fetchone() == values


@pytest.mark.parametrize(
    "field",
    [
        "original_provider_bytes_retained",
        "identity_verified",
        "availability_evidence_verified",
        "decision_eligibility_asserted",
    ],
)
def test_no_promoted_source_flags(field):
    obs = deepcopy(observations())
    obs[0][field] = True
    with pytest.raises(ValueError, match="CONTRACT"):
        codec.derive_records(obs, pins=pins())


@pytest.mark.parametrize("change", ["ordinal", "snapshot", "unknown", "missing", "analytics"])
def test_source_contract_tampering(change):
    obs = deepcopy(observations())
    if change == "ordinal":
        obs[0]["ordinal"] = True
    elif change == "snapshot":
        obs[0]["snapshot_id"] = "d" * 64
    elif change == "unknown":
        obs[0]["extra"] = None
    elif change == "missing":
        del obs[0]["stored_fields"]["volume"]
    else:
        obs[0]["legacy_derived_fields"] = {"iv": "made-up"}
    with pytest.raises(ValueError):
        codec.derive_records(obs, pins=pins())


@pytest.mark.parametrize(
    "name,value",
    [
        ("close", "nan"),
        ("close", "inf"),
        ("close", "1.0"),
        ("volume", "01"),
        ("volume", str(2**63)),
        ("volume", True),
        ("ts", "2026-01-01T00:00:00"),
        ("ts", "2026-01-01T05:30:00+05:30"),
        ("symbol", "x" * 65537),
    ],
    ids=[
        "nan-price",
        "infinite-price",
        "noncanonical-float",
        "noncanonical-integer",
        "integer-overflow",
        "boolean-integer",
        "naive-timestamp",
        "noncanonical-timezone",
        "oversized-text",
    ],
)
def test_exact_stored_cells(name, value):
    obs = deepcopy(observations())
    obs[0]["stored_fields"][name] = value
    with pytest.raises(ValueError):
        codec.derive_records(obs, pins=pins())


def test_duplicate_key_no_winner():
    one = observations()[0]
    two = deepcopy(one)
    two["ordinal"] = 1
    two["stored_fields"]["close"] = (2.0).hex()
    with pytest.raises(ValueError, match="DUPLICATE"):
        codec.derive_records((one, two), pins=pins())


def test_null_key_refused():
    obs = deepcopy(observations())
    obs[0]["stored_fields"]["ts"] = None
    with pytest.raises(ValueError, match="UNKNOWN"):
        codec.derive_records(obs, pins=pins())


def test_empty_and_real_overflow_bound():
    for rows in ((), observations() * 1001):
        with pytest.raises(ValueError, match="BOUNDED"):
            codec.derive_records(rows, pins=pins())


def test_exact_max_rows_and_reconciliation():
    rows = []
    for i in range(1000):
        row = deepcopy(observations()[0])
        row["ordinal"] = i
        row["stored_fields"]["instrument_token"] = str(257 + i)
        rows.append(row)
    result = codec.derive_records(tuple(rows), pins=pins())
    assert len(result) == 1000
    assert [json.loads(r)["source_ordinal"] for r in result] == list(range(1000))


def test_mixed_tables_refused():
    second = observations("option_stream")[0]
    second["ordinal"] = 1
    with pytest.raises(ValueError, match="CONTRACT"):
        codec.derive_records((*observations(), second), pins=pins())


def test_pin_changes_bind_every_row():
    other = codec.LegacyBronzePins("d" * 64, "b" * 64, "c" * 64)
    assert codec.derive_records(observations(), pins=pins()) != codec.derive_records(
        observations(), pins=other
    )
    assert pins().scope_id != other.scope_id


def test_real_aggregate_byte_bound():
    rows = []
    for i in range(70):
        row = deepcopy(observations()[0])
        row["ordinal"] = i
        row["stored_fields"]["instrument_token"] = str(i + 1)
        row["stored_fields"]["symbol"] = "x" * 65536
        rows.append(row)
    with pytest.raises(ValueError, match="BYTE_BOUND"):
        codec.derive_records(tuple(rows), pins=pins())
