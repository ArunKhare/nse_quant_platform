import csv
import io

import pytest

from nse_quant.data_platform.instrument_reference import COLUMNS, parse_instruments, resolve_token


def artifact(*rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return output.getvalue().encode()


def row(**changes):
    values = dict(
        zip(
            COLUMNS,
            (
                "258",
                "1",
                "EXAMPLE",
                "Provider name",
                "123.4500",
                "",
                "0",
                "0.05",
                "1",
                "EQ",
                "NSE",
                "NSE",
            ),
            strict=True,
        )
    )
    values.update(changes)
    return tuple(values[key] for key in COLUMNS)


def test_exact_decimals_and_unresolved_provider_fields():
    snapshot = parse_instruments(artifact(row()))
    assert snapshot.classification == "normalized"
    r = snapshot.records[0]
    assert r.last_price_decimal == "123.4500" and r.expiry is None
    assert r.provider_name == "Provider name" and not hasattr(r, "underlying")


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"instrument_token": "0"}, "INTEGER_RANGE"),
        ({"instrument_token": "4294967296"}, "INTEGER_RANGE"),
        ({"instrument_token": "-1"}, "INVALID_INTEGER"),
        ({"lot_size": "0"}, "INTEGER_RANGE"),
        ({"last_price": "NaN"}, "INVALID_DECIMAL"),
        ({"strike": ""}, "INVALID_DECIMAL"),
        ({"tick_size": "1e-2"}, "INVALID_DECIMAL"),
        ({"expiry": "2026-02-30"}, "INVALID_EXPIRY"),
        ({"instrument_type": "CE"}, "MISSING_DERIVATIVE_EXPIRY"),
        ({"tradingsymbol": " BAD"}, "INVALID_IDENTIFIER"),
        ({"name": "x" * 4097}, "FIELD_SIZE_LIMIT"),
    ],
)
def test_invalid_row_no_salvage(changes, reason):
    snapshot = parse_instruments(artifact(row(), row(**changes)))
    assert snapshot.reason_code == reason and snapshot.failure_row_ordinal == 1
    assert not snapshot.records


@pytest.mark.parametrize(
    "raw,reason",
    [
        (b"", "EMPTY_ARTIFACT"),
        (b"\xff", "INVALID_UTF8"),
        (b"\x00", "NUL_BYTE"),
        (b"bad,header\n", "UNSUPPORTED_HEADER"),
        (artifact(), "EMPTY_SNAPSHOT"),
        (artifact(("short",)), "COLUMN_COUNT"),
        (artifact(row()) + b'"unterminated', "INVALID_CSV"),
    ],
)
def test_malformed(raw, reason):
    snapshot = parse_instruments(raw)
    assert snapshot.reason_code == reason and not snapshot.records


def test_duplicate_tokens_are_ambiguous():
    snapshot = parse_instruments(artifact(row(), row(tradingsymbol="OTHER")))
    result = resolve_token(snapshot, reference_revision_id="a" * 64, instrument_token=258)
    assert result.status == "ambiguous" and result.candidate_row_ordinals == (0, 1)
    assert result.evidence_mode == "PINNED_SNAPSHOT_ONLY"


def test_unique_missing_quarantined_lookup():
    snapshot = parse_instruments(artifact(row()))
    assert (
        resolve_token(snapshot, reference_revision_id="a" * 64, instrument_token=258).status
        == "matched"
    )
    assert (
        resolve_token(snapshot, reference_revision_id="a" * 64, instrument_token=999).status
        == "unresolved"
    )
    assert (
        resolve_token(
            parse_instruments(b"bad"), reference_revision_id="a" * 64, instrument_token=258
        ).reason_code
        == "REFERENCE_QUARANTINED"
    )


@pytest.mark.parametrize("token", [True, 0, -1, 2**32, "258"])
def test_invalid_token(token):
    with pytest.raises(ValueError):
        resolve_token(
            parse_instruments(artifact(row())),
            reference_revision_id="a" * 64,
            instrument_token=token,
        )


def test_bounded_and_deterministic(monkeypatch):
    import nse_quant.data_platform.instrument_reference as module

    raw = artifact(row())
    assert parse_instruments(raw) == parse_instruments(raw)
    monkeypatch.setattr(module, "MAX_ARTIFACT_BYTES", 2)
    assert parse_instruments(b"xxx").reason_code == "ARTIFACT_BYTE_LIMIT"
    monkeypatch.setattr(module, "MAX_ARTIFACT_BYTES", 16777216)
    monkeypatch.setattr(module, "MAX_ROWS", 1)
    assert parse_instruments(artifact(row(), row())).reason_code == "ROW_COUNT_LIMIT"


def test_plan_creates_no_database(tmp_path, capsys):
    from nse_quant.data_platform.instrument_reference_cli import main

    source = tmp_path / "input.csv"
    source.write_bytes(artifact(row()))
    b, s = tmp_path / "bronze.duckdb", tmp_path / "silver.duckdb"
    assert (
        main(
            [
                "import-file",
                "--input",
                str(source),
                "--bronze-db",
                str(b),
                "--import-session-id",
                "session",
                "--source-record-id",
                "r",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "normalize",
                "--bronze-db",
                str(b),
                "--silver-db",
                str(s),
                "--capture-event-id",
                "a" * 64,
                "--envelope-hash",
                "b" * 64,
            ]
        )
        == 0
    )
    assert not b.exists() and not s.exists()
    assert '"inputs_verified": false' in capsys.readouterr().out
