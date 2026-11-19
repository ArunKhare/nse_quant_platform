"""Immutable bounded research-IV bundle artifacts; offline integrity is not verification."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

VERSION = "research-iv-feature-bundle@1"
MODEL_VERSION = "research-european-bsm-iv@1"
MAX_MEMBERS = 64
MAX_MEMBER_BYTES = 16384
MAX_BUNDLE_BYTES = 4194304


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise ValueError("IV_BUNDLE_DUPLICATE_JSON_KEY")
        value[key] = item
    return value


def _invalid(_value: str) -> Any:
    raise ValueError("IV_BUNDLE_NONFINITE_JSON")


def _json(raw: str, limit: int) -> dict[str, Any]:
    if not isinstance(raw, str) or not 0 < len(raw.encode()) <= limit:
        raise ValueError("IV_BUNDLE_COMPONENT_BYTE_LIMIT")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid)
        if not isinstance(value, dict) or canonical(value) != raw:
            raise ValueError("IV_BUNDLE_CANONICAL_OBJECT_REQUIRED")
    except (UnicodeError, RecursionError, OverflowError, json.JSONDecodeError):
        raise ValueError("IV_BUNDLE_MALFORMED_JSON") from None
    return value


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and type(value) in (int, float) and math.isfinite(value)


def _clock(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("IV_BUNDLE_SOURCE_CLOCK_INVALID")
    parsed = datetime.fromisoformat(value)
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or parsed.astimezone(UTC).isoformat() != value
    ):
        raise ValueError("IV_BUNDLE_CANONICAL_UTC_SOURCE_CLOCK_REQUIRED")


@dataclass(frozen=True)
class IvBundleMember:
    build_id: str
    input_id: str
    definition_fingerprint: str
    archive_fingerprint: str
    revalidation_fingerprint: str
    option_build_id: str
    spot_build_id: str
    scenario_terms_sha256: str
    calculation_json: str
    terms_json: str
    source_option_event_ts: str | None = None
    source_spot_event_ts: str | None = None


@dataclass(frozen=True)
class ResearchIvBundle:
    bundle_id: str
    membership_fingerprint: str
    members: tuple[IvBundleMember, ...]
    version: str = VERSION
    evidence_mode: str = "RESEARCH_IV_SNAPSHOT_NOT_PUBLISHED"
    event_ts: None = None
    published_at: None = None
    publication_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    option_underlying_identity_binding_verified: bool = False
    scenario_terms_authoritative: bool = False
    model_suitability_verified: bool = False
    source_acquisition_authenticity_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_contract_id: None = None


CALCULATION_FIELDS = frozenset(
    {
        "calculation_id",
        "model_version",
        "status",
        "reason_codes",
        "input_fingerprint",
        "scipy_version",
        "python_version",
        "implied_volatility",
        "greeks",
        "price_residual",
        "canonical_contract_id",
        "model_suitability_verified",
        "underlying_identity_verified",
        "source_acquisition_authenticity_asserted",
        "availability_evidence_verified",
        "historical_validity_asserted",
        "publication_asserted",
        "decision_eligibility_asserted",
    }
)
GREEK_FIELDS = frozenset(
    {"price", "delta", "gamma", "vega_per_vol_unit", "theta_per_calendar_day", "rho_per_rate_unit"}
)
TERMS_FIELDS = frozenset(
    {"strike", "annual_rate", "annual_dividend_yield", "assumed_years_to_expiry", "option_type"}
)


def validate_member(member: IvBundleMember) -> tuple[str, str, str]:
    if (
        type(member) is not IvBundleMember
        or not all(
            pin(x)
            for x in (
                member.build_id,
                member.input_id,
                member.definition_fingerprint,
                member.archive_fingerprint,
                member.revalidation_fingerprint,
                member.option_build_id,
                member.spot_build_id,
                member.scenario_terms_sha256,
            )
        )
        or member.option_build_id == member.spot_build_id
    ):
        raise ValueError("IV_BUNDLE_EXACT_DISTINCT_MEMBER_PINS_REQUIRED")
    if len(canonical(asdict(member)).encode()) > MAX_MEMBER_BYTES:
        raise ValueError("IV_BUNDLE_MEMBER_BYTE_LIMIT")
    terms = _json(member.terms_json, 4096)
    if (
        set(terms) != TERMS_FIELDS
        or terms["option_type"] not in ("CE", "PE")
        or any(
            not isinstance(terms[key], str)
            or re.fullmatch(r"-?(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,12})?", terms[key]) is None
            for key in TERMS_FIELDS - {"option_type"}
        )
        or sha(canonical([MODEL_VERSION, terms]).encode()) != member.scenario_terms_sha256
    ):
        raise ValueError("IV_BUNDLE_SCENARIO_CONTENT_OR_PIN_MISMATCH")
    expected_input = sha(
        canonical(
            [
                "research-iv-build-record@1",
                member.option_build_id,
                member.spot_build_id,
                member.scenario_terms_sha256,
                member.definition_fingerprint,
            ]
        ).encode()
    )
    if member.input_id != expected_input:
        raise ValueError("IV_BUNDLE_INPUT_GROUP_PIN_MISMATCH")
    numbers = {key: Decimal(terms[key]) for key in TERMS_FIELDS - {"option_type"}}
    if (
        not Decimal("1e-8") <= numbers["strike"] <= Decimal("1e9")
        or not Decimal("-0.25") <= numbers["annual_rate"] <= Decimal("1")
        or not Decimal("-0.25") <= numbers["annual_dividend_yield"] <= Decimal("1")
        or not Decimal("1e-6") <= numbers["assumed_years_to_expiry"] <= Decimal("5")
    ):
        raise ValueError("IV_BUNDLE_SCENARIO_DOMAIN_UNSUPPORTED")
    value = _json(member.calculation_json, 8192)
    if (
        set(value) != CALCULATION_FIELDS
        or value["model_version"] != MODEL_VERSION
        or value["status"] != "computed_research_scenario"
        or not pin(value["input_fingerprint"])
        or not pin(value["calculation_id"])
        or sha(canonical(dict(value, calculation_id="")).encode()) != value["calculation_id"]
        or value["canonical_contract_id"] is not None
        or any(
            value[key] is not False
            for key in (
                "model_suitability_verified",
                "underlying_identity_verified",
                "source_acquisition_authenticity_asserted",
                "availability_evidence_verified",
                "historical_validity_asserted",
                "publication_asserted",
                "decision_eligibility_asserted",
            )
        )
    ):
        raise ValueError("IV_BUNDLE_CALCULATION_IDENTITY_OR_AUTHORITY_MISMATCH")
    if (
        value["reason_codes"] != ["EXPLICIT_EUROPEAN_BSM_SCENARIO_SOLVED"]
        or any(
            not isinstance(value[key], str)
            or re.fullmatch(r"[A-Za-z0-9.+_-]{1,64}", value[key]) is None
            for key in ("scipy_version", "python_version")
        )
        or not _number(value["implied_volatility"])
        or not 0.000001 <= value["implied_volatility"] <= 5.0
        or not _number(value["price_residual"])
    ):
        raise ValueError("IV_BUNDLE_NUMERICAL_PROFILE_FIELDS_INVALID")
    greeks = value["greeks"]
    if (
        not isinstance(greeks, dict)
        or set(greeks) != GREEK_FIELDS
        or any(not _number(greeks[key]) for key in GREEK_FIELDS)
        or greeks["price"] < 0
        or greeks["gamma"] < 0
        or greeks["vega_per_vol_unit"] <= 1e-8
    ):
        raise ValueError("IV_BUNDLE_FINITE_GREEKS_REQUIRED")
    _clock(member.source_option_event_ts)
    _clock(member.source_spot_event_ts)
    # Deduplication is exact scenario-role scope, NOT canonical instrument identity.
    return member.option_build_id, member.spot_build_id, member.scenario_terms_sha256


def _validate(bundle: ResearchIvBundle) -> bytes:
    if (
        type(bundle) is not ResearchIvBundle
        or bundle.version != VERSION
        or bundle.evidence_mode != "RESEARCH_IV_SNAPSHOT_NOT_PUBLISHED"
        or bundle.event_ts is not None
        or bundle.published_at is not None
        or bundle.canonical_contract_id is not None
        or any(
            x is not False
            for x in (
                bundle.publication_asserted,
                bundle.availability_evidence_verified,
                bundle.historical_validity_asserted,
                bundle.option_underlying_identity_binding_verified,
                bundle.scenario_terms_authoritative,
                bundle.model_suitability_verified,
                bundle.source_acquisition_authenticity_asserted,
                bundle.atomic_cross_database_snapshot_asserted,
                bundle.decision_eligibility_asserted,
            )
        )
        or type(bundle.members) is not tuple
        or not 1 <= len(bundle.members) <= MAX_MEMBERS
    ):
        raise ValueError("IV_BUNDLE_RESEARCH_ONLY_CONTRACT_REQUIRED")
    if any(type(member) is not IvBundleMember for member in bundle.members):
        raise TypeError("TYPED_IV_BUNDLE_MEMBERS_REQUIRED")
    ids = tuple(item.build_id for item in bundle.members)
    if ids != tuple(sorted(set(ids))):
        raise ValueError("IV_BUNDLE_UNIQUE_SORTED_BUILD_MEMBERS_REQUIRED")
    scopes = [validate_member(item) for item in bundle.members]
    if len(set(scopes)) != len(scopes):
        raise ValueError("IV_BUNDLE_DUPLICATE_EXACT_SCENARIO_ROLE_SCOPE")
    if len({item.definition_fingerprint for item in bundle.members}) != 1:
        raise ValueError("IV_BUNDLE_MIXED_MODEL_DEFINITIONS_NOT_SUPPORTED")
    # Runtime labels are evidence context, not an assertion that dependencies are installed.
    runtime_pairs = {
        tuple(
            _json(item.calculation_json, 8192)[key] for key in ("scipy_version", "python_version")
        )
        for item in bundle.members
    }
    if len(runtime_pairs) != 1:
        raise ValueError("IV_BUNDLE_MIXED_NUMERICAL_RUNTIMES_NOT_SUPPORTED")
    if bundle.membership_fingerprint != sha(
        canonical(
            [
                VERSION,
                [asdict(item) for item in bundle.members],
            ]
        ).encode()
    ):
        raise ValueError("IV_BUNDLE_MEMBERSHIP_PIN_MISMATCH")
    manifest = asdict(bundle)
    del manifest["bundle_id"]
    raw = canonical(manifest).encode()
    if len(raw) > MAX_BUNDLE_BYTES:
        raise ValueError("IV_BUNDLE_AGGREGATE_BYTE_LIMIT")
    return raw


def make_research_iv_bundle(members: tuple[IvBundleMember, ...]) -> ResearchIvBundle:
    """Untrusted offline constructor: checks consistency, NEVER native source validity."""
    if type(members) is not tuple or not 1 <= len(members) <= MAX_MEMBERS:
        raise ValueError("BOUNDED_IMMUTABLE_IV_BUNDLE_MEMBERS_REQUIRED")
    if any(type(item) is not IvBundleMember for item in members):
        raise TypeError("TYPED_IV_BUNDLE_MEMBERS_REQUIRED")
    ordered = tuple(sorted(members, key=lambda item: item.build_id))
    membership = sha(canonical([VERSION, [asdict(item) for item in ordered]]).encode())
    bundle = ResearchIvBundle("", membership, ordered)
    raw = _validate(bundle)
    return ResearchIvBundle(sha(raw), membership, ordered)


def encode_research_iv_bundle(bundle: ResearchIvBundle) -> bytes:
    raw = _validate(bundle)
    if not pin(bundle.bundle_id) or sha(raw) != bundle.bundle_id:
        raise ValueError("IV_BUNDLE_CHECKSUM_MISMATCH")
    return raw


def decode_research_iv_bundle(raw: bytes, *, expected_bundle_id: str) -> ResearchIvBundle:
    """Offline canonical artifact verification; never publication or current-source check."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BUNDLE_BYTES:
        raise ValueError("BOUNDED_IMMUTABLE_IV_BUNDLE_BYTES_REQUIRED")
    if not pin(expected_bundle_id) or sha(raw) != expected_bundle_id:
        raise ValueError("IV_BUNDLE_CHECKSUM_MISMATCH")
    try:
        value = _json(raw.decode("utf-8"), MAX_BUNDLE_BYTES)
        if set(value) != set(ResearchIvBundle.__dataclass_fields__) - {"bundle_id"}:
            raise ValueError("IV_BUNDLE_EXACT_MANIFEST_SCHEMA_REQUIRED")
        items = value["members"]
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_MEMBERS:
            raise ValueError("IV_BUNDLE_MEMBER_COUNT_INVALID")
        if any(
            not isinstance(item, dict) or set(item) != set(IvBundleMember.__dataclass_fields__)
            for item in items
        ):
            raise ValueError("IV_BUNDLE_EXACT_MEMBER_SCHEMA_REQUIRED")
        bundle = ResearchIvBundle(
            **dict(
                value,
                bundle_id=expected_bundle_id,
                members=tuple(IvBundleMember(**item) for item in items),
            )
        )
        encode_research_iv_bundle(bundle)
    except (UnicodeError, TypeError, KeyError, RecursionError, OverflowError):
        raise ValueError("IV_BUNDLE_MALFORMED_BYTES") from None
    return bundle
