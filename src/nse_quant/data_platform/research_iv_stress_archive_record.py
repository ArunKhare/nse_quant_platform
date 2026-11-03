"""Strict bounded stress-record envelope. Offline consistency is NOT native truth."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

VERSION = "research-iv-spot-stress-archive-record@1"
NATIVE_VERSION = "native-research-iv-fixed-vol-spot-stress@1"
STORE_VERSION = "audited-research-iv-spot-stress-recording@1"
MAX_RECORD_BYTES = 25165824
MAX_NATIVE_BYTES = 8388608
MAX_STUDY_BYTES = 65536
DEFINITION = (
    VERSION,
    STORE_VERSION,
    NATIVE_VERSION,
    "research-iv-fixed-vol-spot-stress@1",
    "research-european-bsm-iv@1",
    "single-record-no-retry-no-publication@1",
)
DENIALS = (
    "portfolio_pnl_asserted",
    "volatility_response_modelled",
    "option_underlying_identity_binding_verified",
    "scenario_terms_authoritative",
    "model_suitability_verified",
    "source_acquisition_authenticity_asserted",
    "availability_evidence_verified",
    "historical_validity_asserted",
    "publication_asserted",
    "decision_eligibility_asserted",
    "atomic_cross_database_snapshot_asserted",
)
FACTS = ("current_source_checked", "exact_native_observations_matched", "stress_results_reproduced")
NULLS = ("canonical_contract_id", "event_ts", "published_at")
OBSERVATION_FIELDS = frozenset(
    (
        *DENIALS,
        *FACTS,
        *NULLS,
        "version",
        "build_id",
        "expected_archive_fingerprint",
        "expected_revalidation_fingerprint",
        "status",
        "reason_codes",
        "before",
        "after",
        "provisional_study",
        "repeated_study",
        "study",
        "evidence_fingerprint",
        "source_option_event_ts",
        "source_spot_event_ts",
    )
)


def pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def request(pins: tuple[str, ...], shocks: tuple[int, ...]) -> dict[str, Any]:
    if type(pins) is not tuple or len(pins) != 3 or not all(pin(p) for p in pins):
        raise ValueError("STRESS_RECORD_THREE_REVIEWED_PINS_REQUIRED")
    if (
        type(shocks) is not tuple
        or not 1 <= len(shocks) <= 16
        or any(type(x) is not int or not -5000 <= x <= 5000 for x in shocks)
        or shocks != tuple(sorted(set(shocks)))
    ):
        raise ValueError("STRESS_RECORD_EXACT_BOUNDED_GRID_REQUIRED")
    return dict(pins=list(pins), shocks_bps=list(shocks))


def scope(value: dict[str, Any]) -> str:
    if (
        type(value) is not dict
        or set(value) != {"pins", "shocks_bps"}
        or type(value["pins"]) is not list
        or type(value["shocks_bps"]) is not list
    ):
        raise ValueError("STRESS_RECORD_EXACT_REQUEST_REQUIRED")
    checked = request(tuple(value["pins"]), tuple(value["shocks_bps"]))
    if set(value) != {"pins", "shocks_bps"} or value != checked:
        raise ValueError("STRESS_RECORD_EXACT_REQUEST_REQUIRED")
    return sha(canonical([DEFINITION, checked]).encode())


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("STRESS_RECORD_DUPLICATE_KEY")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise ValueError("STRESS_RECORD_NONFINITE_JSON")


def _float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("STRESS_RECORD_NONFINITE_FLOAT")
    return value


def _study(value: object, shocks: list[int]) -> None:
    if value is None:
        return
    if type(value) is not dict or len(canonical(value).encode()) > MAX_STUDY_BYTES:
        raise ValueError("STRESS_RECORD_STUDY_BYTE_LIMIT")
    if (
        value.get("version") != "research-iv-fixed-vol-spot-stress@1"
        or value.get("status") != "computed_fixed_iv_hypothetical_spot_stress"
        or value.get("shocks_bps") != shocks
        or not pin(value.get("evidence_fingerprint"))
        or value.get("current_source_checked") is not False
        or any(
            value.get(k) is not False
            for k in DENIALS
            if k != "atomic_cross_database_snapshot_asserted"
        )
        or any(value.get(k) is not None for k in NULLS)
    ):
        raise ValueError("STRESS_RECORD_STUDY_RESEARCH_PROFILE_REQUIRED")
    fields = set(DENIALS) - {"atomic_cross_database_snapshot_asserted"}
    fields.update(
        (
            *NULLS,
            "current_source_checked",
            "version",
            "model_version",
            "spot_decimal",
            "terms",
            "fixed_implied_volatility",
            "shocks_bps",
            "baseline",
            "points",
            "scipy_version",
            "python_version",
            "evidence_fingerprint",
            "status",
        )
    )
    if set(value) != fields or value["model_version"] != "research-european-bsm-iv@1":
        raise ValueError("STRESS_RECORD_EXACT_STUDY_SCHEMA_REQUIRED")
    terms = value["terms"]
    if (
        type(terms) is not dict
        or set(terms)
        != {
            "strike",
            "annual_rate",
            "annual_dividend_yield",
            "assumed_years_to_expiry",
            "option_type",
        }
        or terms["option_type"] not in ("CE", "PE")
        or any(type(v) is not str or not 0 < len(v) <= 64 for v in terms.values())
        or type(value["spot_decimal"]) is not str
        or re.fullmatch(r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,12})?", value["spot_decimal"]) is None
        or type(value["fixed_implied_volatility"]) is not float
        or not 0.000001 <= value["fixed_implied_volatility"] <= 5.0
    ):
        raise ValueError("STRESS_RECORD_STUDY_INPUT_PROFILE_REQUIRED")
    for key in ("scipy_version", "python_version"):
        if (
            type(value[key]) is not str
            or re.fullmatch(r"[A-Za-z0-9.+_-]{1,64}", value[key]) is None
        ):
            raise ValueError("STRESS_RECORD_STUDY_RUNTIME_REQUIRED")

    def greeks(data: Any) -> None:
        if (
            type(data) is not dict
            or set(data)
            != {
                "price",
                "delta",
                "gamma",
                "vega_per_vol_unit",
                "theta_per_calendar_day",
                "rho_per_rate_unit",
            }
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in data.values())
            or any(data[k] < 0 for k in ("price", "gamma", "vega_per_vol_unit"))
        ):
            raise ValueError("STRESS_RECORD_STUDY_VALUES_REQUIRED")

    greeks(value["baseline"])
    points = value["points"]
    if type(points) is not list or len(points) != len(shocks):
        raise ValueError("STRESS_RECORD_GRID_COUNT_MISMATCH")
    for point, shock in zip(points, shocks, strict=True):
        if (
            type(point) is not dict
            or set(point) != {"shock_bps", "shocked_spot_decimal", "values", "model_price_change"}
            or type(point["shock_bps"]) is not int
            or point["shock_bps"] != shock
            or type(point["shocked_spot_decimal"]) is not str
            or re.fullmatch(
                r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,16})?", point["shocked_spot_decimal"]
            )
            is None
            or type(point["model_price_change"]) not in (int, float)
            or not math.isfinite(point["model_price_change"])
        ):
            raise ValueError("STRESS_RECORD_GRID_POINT_REQUIRED")
        greeks(point["values"])
        if point["model_price_change"] != point["values"]["price"] - value["baseline"]["price"]:
            raise ValueError("STRESS_RECORD_MODEL_PRICE_CHANGE_MISMATCH")
    expected = sha(
        canonical(
            [
                value["version"],
                value["model_version"],
                value["spot_decimal"],
                terms,
                value["fixed_implied_volatility"],
                shocks,
                value["baseline"],
                points,
                value["scipy_version"],
                value["python_version"],
            ]
        ).encode()
    )
    if value["evidence_fingerprint"] != expected:
        raise ValueError("STRESS_RECORD_STUDY_FINGERPRINT_MISMATCH")
    # Structural/hash consistency is deliberately not independent BSM or source truth.


def decode(raw: str) -> dict[str, Any]:
    if type(raw) is not str or not 0 < len(raw.encode()) <= MAX_RECORD_BYTES:
        raise ValueError("STRESS_RECORD_BYTE_LIMIT")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_constant=_constant,
            parse_float=_float,
        )
        if (
            type(value) is not dict
            or set(value) != {"version", "definition", "request", "result"}
            or value["version"] != VERSION
            or value["definition"] != list(DEFINITION)
            or canonical(value) != raw
            or type(value["request"]) is not dict
        ):
            raise ValueError("STRESS_RECORD_EXACT_CANONICAL_ENVELOPE_REQUIRED")
        requested = value["request"]
        scope(requested)
        observed = value["result"]
        if (
            type(observed) is not dict
            or set(observed) != OBSERVATION_FIELDS
            or observed["version"] != NATIVE_VERSION
            or [
                observed[k]
                for k in (
                    "build_id",
                    "expected_archive_fingerprint",
                    "expected_revalidation_fingerprint",
                )
            ]
            != requested["pins"]
            or any(observed[k] is not False for k in DENIALS)
            or any(type(observed[k]) is not bool for k in FACTS)
            or any(observed[k] is not None for k in NULLS)
            or observed["status"]
            not in ("computed_current_native_research_iv_spot_stress", "review_required")
        ):
            raise ValueError("STRESS_RECORD_NATIVE_RESULT_CONTRACT_MISMATCH")
        if type(observed["before"]) is not dict:
            raise ValueError("STRESS_RECORD_ORIGINAL_NATIVE_OBSERVATION_REQUIRED")
        reasons = observed["reason_codes"]
        if (
            type(reasons) is not list
            or not 1 <= len(reasons) <= 16
            or any(
                type(c) is not str or re.fullmatch(r"[A-Z0-9_]{1,128}", c) is None for c in reasons
            )
            or len(set(reasons)) != len(reasons)
        ):
            raise ValueError("STRESS_RECORD_REASON_CODES_REQUIRED")
        for name in ("source_option_event_ts", "source_spot_event_ts"):
            clock = observed[name]
            if clock is not None and (type(clock) is not str or not 0 < len(clock) <= 64):
                raise ValueError("STRESS_RECORD_SOURCE_CLOCK_PROFILE")
        for name in ("before", "after"):
            nested = observed[name]
            if nested is not None and (
                type(nested) is not dict or len(canonical(nested).encode()) > MAX_NATIVE_BYTES
            ):
                raise ValueError("STRESS_RECORD_NATIVE_OBSERVATION_BYTE_LIMIT")
        for name in ("provisional_study", "repeated_study", "study"):
            _study(observed[name], requested["shocks_bps"])
        positive = observed["status"] == "computed_current_native_research_iv_spot_stress"
        if positive:
            if (
                not all(observed[k] is True for k in FACTS)
                or not pin(observed["evidence_fingerprint"])
                or observed["before"] is None
                or observed["before"] != observed["after"]
                or observed["study"] is None
                or observed["study"] != observed["provisional_study"]
                or observed["study"] != observed["repeated_study"]
            ):
                raise ValueError("STRESS_RECORD_INCOMPLETE_POSITIVE")
        elif observed["study"] is not None or observed["evidence_fingerprint"] is not None:
            raise ValueError("STRESS_RECORD_REVIEW_CANNOT_ACCEPT_STUDY")
        return value
    except (UnicodeError, RecursionError, OverflowError, json.JSONDecodeError) as error:
        raise ValueError("STRESS_RECORD_MALFORMED_JSON") from error


def encode(requested: dict[str, Any], result: dict[str, Any]) -> str:
    raw = canonical(
        dict(version=VERSION, definition=list(DEFINITION), request=requested, result=result)
    )
    decode(raw)
    return raw
