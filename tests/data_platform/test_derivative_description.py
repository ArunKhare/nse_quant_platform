"""Pure description/codec tests: no source authenticity or native E2E assertion."""

from dataclasses import asdict, replace

import pytest

from nse_quant.data_platform import derivative_description as kernel


def source_row(**changes):
    row = {
        "row_ordinal": 0,
        "instrument_token": 257,
        "exchange_token": "1",
        "tradingsymbol": "PROVIDER_SYMBOL_NOT_PARSED",
        "provider_name": "NIFTY",
        "last_price_decimal": "100.00",
        "expiry": "2026-11-24",
        "strike_decimal": "25000.00",
        "tick_size_decimal": "0.05",
        "lot_size": 1,
        "instrument_type": "CE",
        "segment": "NFO-OPT",
        "exchange": "NFO",
        "source_fields_hash": "b" * 64,
    }
    row.update(changes)
    return row


def describe(**changes):
    return kernel.describe_derivative_row(
        assessment_revision_id="a" * 64, frozen_row_json=kernel.canonical(source_row(**changes))
    )


def test_description_is_not_canonical_identity_or_provenance():
    value = describe()
    assert value.status == "described"
    assert value.normalized_strike == "25000"
    assert value.normalized_tick_size == "0.05"
    assert value.provider_description_key is not None
    assert value.canonical_contract_id is None
    assert value.canonical_underlying_id is None
    assert not value.provenance_verified
    assert not value.historical_validity_asserted
    assert not value.availability_evidence_verified
    assert not value.publication_asserted
    assert not value.decision_eligibility_asserted


def test_equivalent_decimals_share_description_key_but_preserve_exact_evidence():
    first = describe(strike_decimal="025000.000", tick_size_decimal="00.0500")
    second = describe()
    assert first.provider_description_key == second.provider_description_key
    assert first.description_id != second.description_id
    assert first.frozen_row_json != second.frozen_row_json


@pytest.mark.parametrize(
    "changes",
    [
        {"instrument_token": 999},
        {"tradingsymbol": "DIFFERENT"},
        {"lot_size": 2},
        {"tick_size_decimal": "0.01"},
        {"source_fields_hash": "c" * 64},
        {"last_price_decimal": "99"},
        {"row_ordinal": 1},
    ],
)
def test_nonkey_changes_remain_in_description_identity(changes):
    first, second = describe(), describe(**changes)
    assert first.provider_description_key == second.provider_description_key
    assert first.description_id != second.description_id


@pytest.mark.parametrize(
    "changes",
    [
        {"provider_name": "BANKNIFTY"},
        {"expiry": "2026-12-29"},
        {"strike_decimal": "26000"},
        {"instrument_type": "PE"},
    ],
)
def test_descriptive_terms_change_key_without_inventing_identity(changes):
    assert describe().provider_description_key != describe(**changes).provider_description_key


@pytest.mark.parametrize("label", ["", " NIFTY", "nifty", "NIFTY 50"])
def test_never_infer_underlying_from_trading_symbol(label):
    value = describe(provider_name=label, tradingsymbol="NIFTY26NOV25000CE")
    assert value.status == "unresolved"
    assert value.provider_description_key is None
    assert value.canonical_underlying_id is None


@pytest.mark.parametrize(
    "changes",
    [
        {"expiry": None},
        {"lot_size": 0},
        {"tick_size_decimal": None},
        {"tick_size_decimal": "0.000"},
        {"strike_decimal": None},
        {"strike_decimal": "0"},
    ],
)
def test_incomplete_terms_never_become_positive_descriptions(changes):
    value = describe(**changes)
    assert value.status == "unresolved"
    assert value.provider_description_key is None


def test_future_ignores_only_absent_or_zero_strike_in_key():
    first = describe(segment="NFO-FUT", instrument_type="FUT", strike_decimal=None)
    second = describe(segment="NFO-FUT", instrument_type="FUT", strike_decimal="0.00")
    assert first.status == second.status == "described"
    assert first.provider_description_key == second.provider_description_key
    assert first.description_id != second.description_id
    invalid = describe(segment="NFO-FUT", instrument_type="FUT", strike_decimal="1")
    assert invalid.status == "inconsistent"
    assert invalid.provider_description_key is None


@pytest.mark.parametrize(
    "changes",
    [
        {"exchange": "NSE"},
        {"segment": "NFO-FUT"},
        {"instrument_type": "EQ"},
    ],
)
def test_unsupported_observations_retained(changes):
    value = describe(**changes)
    assert value.status == "unsupported"
    assert value.provider_description_key is None


@pytest.mark.parametrize(
    "changes",
    [
        {"instrument_token": True},
        {"row_ordinal": False},
        {"lot_size": True},
        {"instrument_token": 0},
        {"row_ordinal": -1},
        {"lot_size": -1},
        {"strike_decimal": "NaN"},
        {"tick_size_decimal": 0.05},
        {"strike_decimal": "1e5"},
        {"strike_decimal": "-1"},
        {"strike_decimal": "1."},
        {"expiry": "2026-02-30"},
        {"expiry": "2026-1-1"},
        {"source_fields_hash": "bad"},
        {"exchange_token": "4294967296"},
        {"provider_name": "A" * 4097},
    ],
)
def test_schema_numeric_and_resource_failures_raise(changes):
    with pytest.raises(ValueError):
        describe(**changes)


def test_exact_decimal_handling_does_not_round_large_values():
    value = describe(strike_decimal="123456789012345678901234567890.1234567890123456789")
    assert value.normalized_strike == "123456789012345678901234567890.1234567890123456789"


@pytest.mark.parametrize(
    "value",
    [
        describe(),
        describe(provider_name=""),
        describe(exchange="NSE"),
    ],
)
def test_codec_roundtrip_for_positive_and_nonpositive_results(value):
    raw = kernel.encode_derivative_description(value)
    decoded = kernel.decode_derivative_description(
        raw, expected_description_id=value.description_id
    )
    assert decoded == value


@pytest.mark.parametrize(
    "changes",
    [
        {"provenance_verified": True},
        {"decision_eligibility_asserted": True},
        {"canonical_contract_id": "invented"},
        {"status": "VERIFIED_IDENTITY"},
        {"historical_validity_asserted": 0},
    ],
)
def test_self_hashes_cannot_upgrade_authority(changes):
    value = describe()
    altered = asdict(value)
    altered.update(changes)
    with pytest.raises(ValueError):
        kernel.decode_derivative_description(
            kernel.canonical(altered).encode(),
            expected_description_id=value.description_id,
        )
    with pytest.raises(ValueError):
        kernel.encode_derivative_description(replace(value, **changes))


@pytest.mark.parametrize("kind", ["duplicate", "nonfinite", "whitespace"])
def test_strict_canonical_json(kind):
    value = describe()
    raw = kernel.encode_derivative_description(value)
    if kind == "duplicate":
        raw = raw.replace(b'"status":', b'"status":"bad","status":', 1)
    elif kind == "nonfinite":
        raw = raw.replace(b'"provenance_verified":false', b'"provenance_verified":NaN', 1)
    else:
        raw += b" "
    with pytest.raises(ValueError):
        kernel.decode_derivative_description(raw, expected_description_id=value.description_id)


def test_bounds(monkeypatch):
    value = describe()
    raw = kernel.encode_derivative_description(value)
    monkeypatch.setattr(kernel, "MAX_DESCRIPTION_BYTES", 1)
    with pytest.raises(ValueError):
        kernel.decode_derivative_description(raw, expected_description_id=value.description_id)
    monkeypatch.setattr(kernel, "MAX_ROW_BYTES", 1)
    with pytest.raises(ValueError):
        describe()


def test_default_cli_plan_no_io(tmp_path, capsys):
    from nse_quant.data_platform.derivative_description_cli import main

    assert (
        main(
            [
                "--bronze-db",
                str(tmp_path / "bronze.duckdb"),
                "--reference-db",
                str(tmp_path / "silver.duckdb"),
                "--assessment-id",
                "a" * 64,
                "--instrument-token",
                "257",
            ]
        )
        == 0
    )
    assert list(tmp_path.iterdir()) == []
    assert "PLANNED" in capsys.readouterr().out


def test_cli_plan_does_not_import_execution_dependencies(tmp_path, monkeypatch):
    import builtins

    from nse_quant.data_platform.derivative_description_cli import main

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"duckdb", "nse_quant.data_platform.native_derivative_description"}:
            raise AssertionError("Plan imported execution")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert (
        main(
            [
                "--bronze-db",
                str(tmp_path / "absent-bronze.duckdb"),
                "--reference-db",
                str(tmp_path / "absent-silver.duckdb"),
                "--assessment-id",
                "a" * 64,
                "--instrument-token",
                "257",
            ]
        )
        == 0
    )
    assert list(tmp_path.iterdir()) == []
