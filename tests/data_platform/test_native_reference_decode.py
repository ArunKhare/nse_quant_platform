import csv
import gzip
import io

import pytest

from nse_quant.data_platform.native_reference_decode import (
    COLUMNS,
    normalize_native_content,
    parse_native_csv,
)


def fixture_csv(**changes):
    row = dict(
        zip(
            COLUMNS,
            ("408065", "1594", "INFY", "INFOSYS", "0", "", "", "0.05", "1", "EQ", "NSE", "NSE"),
            strict=True,
        )
    )
    row.update(changes)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(COLUMNS)
    writer.writerow([row[k] for k in COLUMNS])
    return output.getvalue().encode()


def test_official_equity_missing_strike_and_provider_name():
    result = parse_native_csv(fixture_csv())
    assert result.classification == "normalized"
    row = result.rows[0]
    assert row.strike_decimal is None and row.expiry is None
    assert row.provider_name == "INFOSYS" and row.row_ordinal == 0
    assert not hasattr(row, "underlying")


def test_future_missing_strike_and_exact_option_decimal():
    future = parse_native_csv(fixture_csv(instrument_type="FUT", expiry="2026-11-26"))
    assert future.rows[0].strike_decimal is None
    option = parse_native_csv(
        fixture_csv(
            instrument_type="CE", expiry="2026-11-26", strike="25000.0000", last_price="123.4500"
        )
    )
    assert option.rows[0].strike_decimal == "25000.0000"
    assert option.rows[0].last_price_decimal == "123.4500"


@pytest.mark.parametrize("encoding", [None, "identity", "gzip", "GZIP"])
def test_supported_content(encoding):
    raw = fixture_csv()
    encoded = gzip.compress(raw, mtime=0) if encoding and encoding.lower() == "gzip" else raw
    headers: tuple[tuple[str, str], ...] = (("content-type", "text/csv; charset=utf-8"),)
    if encoding:
        headers += (("content-encoding", encoding),)
    result = normalize_native_content(encoded, headers)
    assert result.classification == "normalized" and len(result.rows) == 1


@pytest.mark.parametrize("variant", ["truncated", "crc", "trailing", "members", "not-gzip"])
def test_no_gzip_salvage(variant):
    raw = gzip.compress(fixture_csv(), mtime=0)
    variants = {
        "truncated": raw[:-2],
        "crc": raw[:-8] + b"bad!" + raw[-4:],
        "trailing": raw + b"extra",
        "members": raw + raw,
        "not-gzip": b"csv",
    }
    result = normalize_native_content(variants[variant], (("content-encoding", "gzip"),))
    assert result.classification == "quarantine" and not result.rows
    assert result.decoded_payload_hash is None


@pytest.mark.parametrize(
    "headers,reason",
    [
        ((("content-encoding", "br"),), "UNSUPPORTED_CONTENT_ENCODING"),
        ((("content-encoding", "gzip, identity"),), "UNSUPPORTED_CONTENT_ENCODING"),
        ((("content-encoding", "gzip"), ("content-encoding", "gzip")), "AMBIGUOUS_CONTENT_HEADERS"),
        ((("content-type", "text/html"),), "UNSUPPORTED_MEDIA_TYPE"),
        ((("content-type", "text/csv; charset=latin1"),), "UNSUPPORTED_CHARSET"),
    ],
)
def test_header_policy(headers, reason):
    assert normalize_native_content(fixture_csv(), headers).reason_code == reason


def test_gzip_bomb_bound(monkeypatch):
    import nse_quant.data_platform.native_reference_decode as module

    monkeypatch.setattr(module, "MAX_DECODED_BYTES", 100)
    result = normalize_native_content(gzip.compress(b"x" * 10000), (("content-encoding", "gzip"),))
    assert result.reason_code == "DECODED_BYTE_LIMIT" and not result.rows


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"instrument_token": "0"}, "INTEGER_RANGE"),
        ({"instrument_token": "4294967296"}, "INTEGER_RANGE"),
        ({"lot_size": "-1"}, "INVALID_INTEGER"),
        ({"last_price": "NaN"}, "INVALID_DECIMAL"),
        ({"strike": "-2"}, "INVALID_DECIMAL"),
        ({"expiry": "2026-02-30"}, "INVALID_EXPIRY"),
        ({"instrument_type": "CE"}, "MISSING_DERIVATIVE_EXPIRY"),
        ({"instrument_type": "CE", "expiry": "2026-11-26"}, "MISSING_OPTION_STRIKE"),
        ({"exchange": " NSE"}, "INVALID_IDENTIFIER"),
    ],
)
def test_csv_validation(changes, reason):
    assert parse_native_csv(fixture_csv(**changes)).reason_code == reason


def test_utf8_csv_error_and_no_partial_rows():
    assert parse_native_csv(b"\xff").reason_code == "INVALID_CSV_UTF8"
    assert parse_native_csv(fixture_csv() + b'"broken').reason_code == "MALFORMED_CSV"
    result = parse_native_csv(fixture_csv() + b"bad,row\n")
    assert result.reason_code == "CSV_COLUMN_COUNT" and not result.rows


def test_duplicate_tokens_preserved_and_no_magic_sniffing():
    raw = fixture_csv()
    result = parse_native_csv(raw + raw.split(b"\n", 1)[1])
    assert len(result.rows) == 2 and [r.row_ordinal for r in result.rows] == [0, 1]
    assert normalize_native_content(gzip.compress(raw), ()).classification == "quarantine"


def test_input_and_row_limits(monkeypatch):
    import nse_quant.data_platform.native_reference_decode as module

    monkeypatch.setattr(module, "MAX_ENCODED_BYTES", 1)
    assert normalize_native_content(b"xx", ()).reason_code == "ENCODED_BYTE_LIMIT"
    monkeypatch.setattr(module, "MAX_ROWS", 0)
    assert parse_native_csv(fixture_csv()).reason_code == "ROW_COUNT_LIMIT"


def test_plan_side_effect_free(tmp_path, capsys):
    from nse_quant.data_platform.native_reference_cli import main

    args = [
        "--bronze-db",
        str(tmp_path / "bronze.duckdb"),
        "--silver-db",
        str(tmp_path / "silver.duckdb"),
        "--initialize",
    ]
    for name in (
        "body-capture-event-id",
        "body-envelope-hash",
        "metadata-capture-event-id",
        "metadata-envelope-hash",
    ):
        args += ["--" + name, "a" * 64]
    assert main(args) == 0 and not list(tmp_path.iterdir())
    assert '"inputs_verified": false' in capsys.readouterr().out
