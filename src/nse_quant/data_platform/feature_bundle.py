"""Canonical immutable quote-bundle candidates. Checksums are not publication."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BUNDLE_VERSION = "quote-feature-bundle@1"
GOLD_READER_VERSION = "gold-provider-price-consumer@1"
FEATURE_VERSION = "provider-packet-price-fields@1"
MAX_MEMBERS = 64
MAX_MEMBER_BYTES = 1_048_576
MAX_BUNDLE_BYTES = 4_194_304
CANDIDATE_FIELDS = frozenset(
    {
        "build_id",
        "feature_version",
        "definition_fingerprint",
        "source_assessment_revision_id",
        "status",
        "reason_code",
        "source_evidence_fingerprint",
        "source_association_fingerprint",
        "source_frame_revision_id",
        "source_packet_ordinal",
        "reference_assessment_revision_id",
        "reference_row_ordinal",
        "reference_source_fields_hash",
        "provider_token",
        "price_divisor",
        "event_ts",
        "last_trade_time",
        "features",
        "quality_flags",
        "canonical_contract_id",
        "published_at",
        "effective_from",
        "effective_to",
        "decision_eligibility_asserted",
    }
)
FEATURE_NAMES = (
    "last_price",
    "average_price",
    "open",
    "high",
    "low",
    "close",
    "intra_packet_range",
)


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def valid_pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_BUNDLE_JSON_KEY")
            result[key] = value
        return result

    def invalid(_value: str) -> Any:
        raise ValueError("NONFINITE_BUNDLE_JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _integer(value: object, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _time(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError("INVALID_BUNDLE_EVENT_TIME")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("AWARE_BUNDLE_EVENT_TIME_REQUIRED")
    if parsed.astimezone(UTC).isoformat() != value:
        raise ValueError("CANONICAL_UTC_BUNDLE_TIME_REQUIRED")


def _decimal(number: int, divisor: int) -> str:
    whole, fraction = divmod(abs(number), divisor)
    digits = len(str(divisor)) - 1
    return f"{'-' if number < 0 else ''}{whole}.{fraction:0{digits}d}"


@dataclass(frozen=True)
class QuoteBundleMember:
    build_id: str
    gold_reader_version: str
    evidence_fingerprint: str
    successful_attempt_job_ids: tuple[str, ...]
    candidate_sha256: str
    candidate_json: str


@dataclass(frozen=True)
class QuoteFeatureBundle:
    bundle_id: str
    membership_fingerprint: str
    members: tuple[QuoteBundleMember, ...]
    bundle_version: str = BUNDLE_VERSION
    evidence_mode: str = "CURRENT_GOLD_SNAPSHOTS_NOT_PUBLISHED"
    published_at: None = None
    publication_asserted: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False


def _validate_candidate(member: QuoteBundleMember) -> tuple[str, int, str]:
    encoded = member.candidate_json.encode()
    if len(encoded) > MAX_MEMBER_BYTES or digest(encoded) != member.candidate_sha256:
        raise ValueError("BUNDLE_MEMBER_BYTES_NOT_VERIFIED")
    value = _json(member.candidate_json)
    if not isinstance(value, dict) or set(value) != CANDIDATE_FIELDS:
        raise ValueError("BUNDLE_CANDIDATE_SCHEMA_MISMATCH")
    if canonical(value) != member.candidate_json:
        raise ValueError("NONCANONICAL_BUNDLE_CANDIDATE")
    if (
        value["build_id"] != member.build_id
        or digest(canonical(dict(value, build_id="")).encode()) != member.build_id
        or value["feature_version"] != FEATURE_VERSION
        or value["status"] != "candidate"
        or value["reason_code"] != "EXACT_PROVIDER_PRICE_FIELDS"
        or value["canonical_contract_id"] is not None
        or value["decision_eligibility_asserted"] is not False
        or any(value[key] is not None for key in ("published_at", "effective_from", "effective_to"))
    ):
        raise ValueError("BUNDLE_CANDIDATE_IDENTITY_OR_STATUS_MISMATCH")
    for key in (
        "definition_fingerprint",
        "source_assessment_revision_id",
        "source_evidence_fingerprint",
        "source_association_fingerprint",
        "source_frame_revision_id",
        "reference_assessment_revision_id",
        "reference_source_fields_hash",
    ):
        if not valid_pin(value[key]):
            raise ValueError("INVALID_BUNDLE_SOURCE_PIN")
    if (
        not _integer(value["source_packet_ordinal"], 4095)
        or not _integer(value["reference_row_ordinal"], 199999)
        or not _integer(value["provider_token"], 2**32 - 1)
        or value["provider_token"] == 0
        or type(value["price_divisor"]) is not int
        or value["price_divisor"] not in {100, 10_000, 10_000_000}
    ):
        raise ValueError("INVALID_BUNDLE_SOURCE_REFERENCE")
    segment = value["provider_token"] & 255
    expected_divisor = 10_000_000 if segment == 3 else 10_000 if segment in {6, 12} else 100
    if segment not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 12} or value["price_divisor"] != expected_divisor:
        raise ValueError("BUNDLE_PROVIDER_SCALE_MISMATCH")
    _time(value["event_ts"])
    _time(value["last_trade_time"])
    features = value["features"]
    if not isinstance(features, list) or not 1 <= len(features) <= len(FEATURE_NAMES):
        raise ValueError("INVALID_BUNDLE_FEATURES")
    names: list[str] = []
    values: dict[str, int] = {}
    for feature in features:
        if not isinstance(feature, dict) or set(feature) != {
            "name",
            "numerator",
            "denominator",
            "decimal_value",
        }:
            raise ValueError("INVALID_BUNDLE_FEATURE_SCHEMA")
        name, number, divisor = feature["name"], feature["numerator"], feature["denominator"]
        if (
            not isinstance(name, str)
            or name not in FEATURE_NAMES
            or type(number) is not int
            or not -(2**32 - 1) <= number <= 2**32 - 1
            or (name != "intra_packet_range" and number < 0)
            or type(divisor) is not int
            or divisor != value["price_divisor"]
            or feature["decimal_value"] != _decimal(number, divisor)
        ):
            raise ValueError("BUNDLE_EXACT_PRICE_MISMATCH")
        names.append(name)
        values[name] = number
    if (
        "last_price" not in names
        or len(set(names)) != len(names)
        or (
            bool({"open", "high", "low", "close"} & set(names))
            and not {
                "open",
                "high",
                "low",
                "close",
            }
            <= set(names)
        )
        or ("average_price" in names and "open" not in names)
        or names != [name for name in FEATURE_NAMES if name in names]
        or (("high" in names and "low" in names) != ("intra_packet_range" in names))
        or (
            "intra_packet_range" in names
            and values["intra_packet_range"] != (values["high"] - values["low"])
        )
    ):
        raise ValueError("BUNDLE_FEATURE_MEMBERSHIP_MISMATCH")
    flags = value["quality_flags"]
    if (
        not isinstance(flags, list)
        or len(flags) > 16
        or any(
            not isinstance(flag, str) or not re.fullmatch(r"[A-Z0-9_]{1,128}", flag)
            for flag in flags
        )
        or len(set(flags)) != len(flags)
    ):
        raise ValueError("INVALID_BUNDLE_QUALITY_FLAGS")
    expected_flags = [
        "ZERO_" + name.upper()
        for name in FEATURE_NAMES[:-1]
        if name in values and values[name] == 0
    ]
    if values.get("intra_packet_range", 0) < 0:
        expected_flags.append("INVERTED_HIGH_LOW")
    if value["event_ts"] is None:
        expected_flags.append("EXCHANGE_EVENT_TIME_UNKNOWN")
    if flags != expected_flags:
        raise ValueError("BUNDLE_QUALITY_FLAGS_MISMATCH")
    return value["source_frame_revision_id"], value["source_packet_ordinal"], FEATURE_VERSION


def _manifest(bundle: QuoteFeatureBundle) -> dict[str, object]:
    value = asdict(bundle)
    del value["bundle_id"]
    return value


def _validate(bundle: QuoteFeatureBundle) -> bytes:
    if (
        bundle.bundle_version != BUNDLE_VERSION
        or bundle.evidence_mode != "CURRENT_GOLD_SNAPSHOTS_NOT_PUBLISHED"
        or bundle.published_at is not None
        or bundle.publication_asserted is not False
        or bundle.historical_validity_asserted is not False
        or bundle.decision_eligibility_asserted is not False
        or not isinstance(bundle.members, tuple)
        or not 1 <= len(bundle.members) <= MAX_MEMBERS
    ):
        raise ValueError("BUNDLE_CONTRACT_MISMATCH")
    build_ids = tuple(member.build_id for member in bundle.members)
    if build_ids != tuple(sorted(set(build_ids))):
        raise ValueError("BUNDLE_MEMBERS_MUST_BE_UNIQUE_AND_SORTED")
    semantic_keys: set[tuple[str, int, str]] = set()
    for member in bundle.members:
        if (
            not valid_pin(member.build_id)
            or not valid_pin(member.evidence_fingerprint)
            or member.gold_reader_version != GOLD_READER_VERSION
            or not isinstance(member.successful_attempt_job_ids, tuple)
            or not 1 <= len(member.successful_attempt_job_ids) <= 1000
            or any(
                not isinstance(job, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job)
                for job in member.successful_attempt_job_ids
            )
            or tuple(sorted(set(member.successful_attempt_job_ids)))
            != (member.successful_attempt_job_ids)
        ):
            raise ValueError("BUNDLE_MEMBER_EVIDENCE_CONTRACT_MISMATCH")
        key = _validate_candidate(member)
        if key in semantic_keys:
            raise ValueError("DUPLICATE_BUNDLE_PACKET_FEATURE_KEY")
        semantic_keys.add(key)
    if bundle.membership_fingerprint != digest(canonical([BUNDLE_VERSION, build_ids]).encode()):
        raise ValueError("BUNDLE_MEMBERSHIP_FINGERPRINT_MISMATCH")
    raw = canonical(_manifest(bundle)).encode()
    if len(raw) > MAX_BUNDLE_BYTES:
        raise ValueError("BUNDLE_BYTE_LIMIT")
    return raw


def make_quote_bundle(members: tuple[QuoteBundleMember, ...]) -> QuoteFeatureBundle:
    """Pure untrusted-input constructor. Content integrity is NOT source verification."""
    if not isinstance(members, tuple) or not 1 <= len(members) <= MAX_MEMBERS:
        raise ValueError("BOUNDED_NONEMPTY_BUNDLE_MEMBERS_REQUIRED")
    if any(
        not isinstance(member, QuoteBundleMember) or not valid_pin(member.build_id)
        for member in members
    ):
        raise ValueError("INVALID_BUNDLE_MEMBER_PIN")
    ordered = tuple(sorted(members, key=lambda member: member.build_id))
    pins = tuple(member.build_id for member in ordered)
    membership = digest(canonical([BUNDLE_VERSION, pins]).encode())
    bundle = QuoteFeatureBundle("", membership, ordered)
    raw = _validate(bundle)
    return QuoteFeatureBundle(digest(raw), membership, ordered)


def encode_quote_bundle(bundle: QuoteFeatureBundle) -> bytes:
    raw = _validate(bundle)
    if not valid_pin(bundle.bundle_id) or digest(raw) != bundle.bundle_id:
        raise ValueError("BUNDLE_CHECKSUM_MISMATCH")
    return raw


def decode_quote_bundle(raw: bytes, *, expected_bundle_id: str) -> QuoteFeatureBundle:
    """Offline bytes/checksum validation, NOT current-source or publication verification."""
    if not isinstance(raw, bytes) or len(raw) > MAX_BUNDLE_BYTES:
        raise ValueError("BOUNDED_EXACT_BUNDLE_BYTES_REQUIRED")
    if not valid_pin(expected_bundle_id) or digest(raw) != expected_bundle_id:
        raise ValueError("BUNDLE_CHECKSUM_MISMATCH")
    try:
        value = _json(raw.decode("utf-8"))
        expected_keys = set(QuoteFeatureBundle.__dataclass_fields__) - {"bundle_id"}
        if not isinstance(value, dict) or set(value) != expected_keys:
            raise ValueError("BUNDLE_SCHEMA_MISMATCH")
        if canonical(value).encode() != raw:
            raise ValueError("NONCANONICAL_BUNDLE_BYTES")
        items = value["members"]
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_MEMBERS:
            raise ValueError("BOUNDED_NONEMPTY_BUNDLE_MEMBERS_REQUIRED")
        members = []
        for item in items:
            if not isinstance(item, dict) or set(item) != set(
                QuoteBundleMember.__dataclass_fields__
            ):
                raise ValueError("BUNDLE_MEMBER_SCHEMA_MISMATCH")
            if not isinstance(item["successful_attempt_job_ids"], list):
                raise ValueError("INVALID_BUNDLE_ATTEMPT_LIST")
            fields = dict(
                item, successful_attempt_job_ids=tuple(item["successful_attempt_job_ids"])
            )
            members.append(QuoteBundleMember(**fields))
        fields = dict(value, members=tuple(members), bundle_id=expected_bundle_id)
        bundle = QuoteFeatureBundle(**fields)
        encode_quote_bundle(bundle)
        return bundle
    except (
        UnicodeError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        OverflowError,
    ) as error:
        raise ValueError("MALFORMED_BUNDLE_BYTES") from error


def read_quote_bundle_file(root: Path, *, bundle_id: str) -> QuoteFeatureBundle:
    """Bounded read of an already-acquired artifact; never initializes or writes."""
    if not valid_pin(bundle_id):
        raise ValueError("EXACT_BUNDLE_PIN_REQUIRED")
    with (root / (bundle_id + ".json")).open("rb") as handle:
        raw = handle.read(MAX_BUNDLE_BYTES + 1)
    return decode_quote_bundle(raw, expected_bundle_id=bundle_id)
