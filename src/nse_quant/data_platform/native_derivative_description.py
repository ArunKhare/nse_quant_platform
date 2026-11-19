"""Pinned current native-reference observation -> nonauthoritative derivative description."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from nse_quant.data_platform.derivative_description import (
    MAX_ROW_BYTES,
    DerivativeDescription,
    canonical,
    describe_derivative_row,
)
from nse_quant.data_platform.native_reference_decode import CSV_VERSION
from nse_quant.data_platform.native_reference_reader import (
    MAX_RESULT_BYTES,
    NativeReferenceLookup,
    _name,
    lookup_native_reference,
)
from nse_quant.data_platform.reference_supersession import RESOLVER_VERSION

VERSION = "native-pinned-derivative-description@1"


@dataclass(frozen=True)
class NativeDerivativeDescription:
    version: str
    assessment_revision_id: str
    instrument_token: int
    status: str
    reason_codes: tuple[str, ...]
    description: DerivativeDescription | None = None
    native_reference_lookup_verified: bool = False
    canonical_identity_asserted: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False


def _matched(value: NativeReferenceLookup, pin: str, token: int) -> bool:
    return (
        value.resolver_version == RESOLVER_VERSION
        and value.evidence_mode == "PINNED_CURRENT_EVIDENCE_ONLY"
        and value.assessment_revision_id == pin
        and value.instrument_token == token
        and value.status == "matched"
        and value.reason_code == "UNIQUE_TOKEN_ROW"
        and len(value.candidates) == 1
        and value.candidates[0].assessment_revision_id == pin
        and value.canonical_contract_id is None
        and value.historical_validity_asserted is False
        and value.publication_asserted is False
    )


def read_native_derivative_description(
    bronze: Any,
    silver: Any,
    *,
    assessment_revision_id: str,
    instrument_token: int,
) -> NativeDerivativeDescription:
    """Owned read-only inputs; no writes or enclosing transactions.

    Inherit native lookup source/audit checks and bounds, not stronger audit coverage.
    Two matching source lookups and row projections detect observed drift only.
    SQL/source errors propagate; blocked/ambiguous lookup never supplies guessed terms.
    """

    def blocked(reason: str) -> NativeDerivativeDescription:
        return NativeDerivativeDescription(
            VERSION,
            assessment_revision_id,
            instrument_token,
            "blocked",
            (reason,),
        )

    if CSV_VERSION != "kite-native-reference-csv@1":
        raise ValueError("UNSUPPORTED_DERIVATIVE_REFERENCE_CSV_VERSION")
    for connection in (bronze, silver):
        current = connection.execute("SELECT current_database()").fetchone()
        attached = connection.execute("PRAGMA database_list").fetchall()
        if current is None or not any(r[1] == current[0] and r[2] for r in attached):
            raise ValueError("FILE_BACKED_DERIVATIVE_REFERENCE_INPUTS_REQUIRED")
    first = lookup_native_reference(
        bronze,
        silver,
        assessment_revision_id=assessment_revision_id,
        instrument_token=instrument_token,
    )
    if not _matched(first, assessment_revision_id, instrument_token):
        return blocked("NATIVE_REFERENCE_NOT_UNIQUE_CURRENT_MATCH")
    row_pin = first.candidates[0]
    if type(row_pin.row_ordinal) is not int or not 0 <= row_pin.row_ordinal < 200000:
        return blocked("NATIVE_REFERENCE_ROW_PIN_INVALID")
    table = _name(silver, "silver", "kite_http_reference_results")

    def projection() -> str | None:
        result = silver.execute(
            f"SELECT CASE WHEN octet_length(encode(result_json))<=? THEN "
            f"CASE WHEN octet_length(encode(CAST(json_extract(result_json, ?) AS VARCHAR)))<=? "
            f"THEN CAST(json_extract(result_json, ?) AS VARCHAR) END END "
            f"FROM {table} WHERE revision_id=?",
            [
                MAX_RESULT_BYTES,
                f"$.rows[{row_pin.row_ordinal}]",
                MAX_ROW_BYTES,
                f"$.rows[{row_pin.row_ordinal}]",
                assessment_revision_id,
            ],
        ).fetchone()
        return result[0] if result is not None else None

    raw = projection()
    if raw is None:
        return blocked("NATIVE_REFERENCE_ROW_PROJECTION_LIMIT_OR_MISSING")
    # DuckDB JSON projection preserves values, not whitespace; freeze canonical values.
    from nse_quant.data_platform.derivative_description import _json

    fields = _json(raw)
    description = describe_derivative_row(
        assessment_revision_id=assessment_revision_id, frozen_row_json=canonical(fields)
    )
    if (
        fields["row_ordinal"] != row_pin.row_ordinal
        or fields["instrument_token"] != instrument_token
        or fields["source_fields_hash"] != row_pin.source_fields_hash
    ):
        return blocked("NATIVE_REFERENCE_PROJECTED_PIN_MISMATCH")
    second = lookup_native_reference(
        bronze,
        silver,
        assessment_revision_id=assessment_revision_id,
        instrument_token=instrument_token,
    )
    if (
        not _matched(second, assessment_revision_id, instrument_token)
        or asdict(first) != asdict(second)
        or projection() != raw
    ):
        return blocked("NATIVE_REFERENCE_OBSERVATION_DRIFT")
    return NativeDerivativeDescription(
        VERSION,
        assessment_revision_id,
        instrument_token,
        description.status,
        description.reason_codes,
        description,
        True,
    )
