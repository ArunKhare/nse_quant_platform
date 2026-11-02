"""Bounded immutable bundle archive bytes; integrity is not native source truth."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

VERSION = "research-iv-bundle-archive-record@1"
ASSEMBLY_VERSION = "native-research-iv-bundle-assembly@1"
MAX_RESULT_BYTES = 25165824
MAX_REQUEST_BYTES = 16384
MAX_LINK_BYTES = 32768
FLAGS = frozenset(
    {
        "publication_asserted",
        "availability_evidence_verified",
        "historical_validity_asserted",
        "option_underlying_identity_binding_verified",
        "scenario_terms_authoritative",
        "model_suitability_verified",
        "source_acquisition_authenticity_asserted",
        "decision_eligibility_asserted",
        "atomic_cross_database_snapshot_asserted",
    }
)
ASSEMBLY_FIELDS = FLAGS | {
    "version",
    "status",
    "reason_codes",
    "requests",
    "first_pass",
    "second_pass",
    "bundle",
    "all_members_revalidated",
    "evidence_fingerprint",
    "canonical_contract_id",
}
REVALIDATION_FIELDS = (
    FLAGS
    - {
        "model_suitability_verified",
        "source_acquisition_authenticity_asserted",
    }
) | {
    "version",
    "build_id",
    "expected_archive_fingerprint",
    "status",
    "reason_codes",
    "archive_before",
    "archive_after",
    "fresh_before",
    "fresh_after",
    "comparison",
    "archived_recording_verified",
    "current_source_checked",
    "exact_recording_reproduced",
    "archive_unchanged_observed",
    "evidence_fingerprint",
    "canonical_contract_id",
}


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("IV_BUNDLE_ARCHIVE_DUPLICATE_KEY")
        result[key] = value
    return result


def _invalid(_value: str) -> Any:
    raise ValueError("IV_BUNDLE_ARCHIVE_NONFINITE_JSON")


def checked(raw: str, limit: int) -> Any:
    if type(raw) is not str or not 0 < len(raw.encode()) <= limit:
        raise ValueError("IV_BUNDLE_ARCHIVE_BYTE_LIMIT")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid)
        if canonical(value) != raw:
            raise ValueError("IV_BUNDLE_ARCHIVE_CANONICAL_BYTES_REQUIRED")
    except (UnicodeError, RecursionError, OverflowError, json.JSONDecodeError):
        raise ValueError("IV_BUNDLE_ARCHIVE_MALFORMED_JSON") from None
    return value


def requests_value(raw: str) -> list[dict[str, str]]:
    value = checked(raw, MAX_REQUEST_BYTES)
    if not isinstance(value, list) or not 1 <= len(value) <= 64:
        raise ValueError("IV_BUNDLE_ARCHIVE_REQUEST_COUNT")
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"build_id", "expected_archive_fingerprint"}
            or not all(pin(x) for x in item.values())
        ):
            raise ValueError("IV_BUNDLE_ARCHIVE_EXACT_REQUEST_PINS_REQUIRED")
    ids = [item["build_id"] for item in value]
    if ids != sorted(set(ids)):
        raise ValueError("IV_BUNDLE_ARCHIVE_UNIQUE_SORTED_REQUESTS_REQUIRED")
    return value


def scope_id(requests_json: str, definition_hash: str) -> str:
    requests_value(requests_json)
    if not pin(definition_hash):
        raise ValueError("IV_BUNDLE_ARCHIVE_DEFINITION_PIN_REQUIRED")
    return sha(canonical([VERSION, requests_json, definition_hash]).encode())


def _reasons(value: object) -> None:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= 64
        or any(type(x) is not str or re.fullmatch(r"[A-Z0-9_]{1,128}", x) is None for x in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError("IV_BUNDLE_ARCHIVE_REASON_CODES_REQUIRED")


def result_value(raw: str, requests_json: str) -> dict[str, Any]:
    requests = requests_value(requests_json)
    value = checked(raw, MAX_RESULT_BYTES)
    if (
        not isinstance(value, dict)
        or set(value) != ASSEMBLY_FIELDS
        or value["version"] != ASSEMBLY_VERSION
        or value["requests"] != requests
        or value["canonical_contract_id"] is not None
        or any(value[key] is not False for key in FLAGS)
    ):
        raise ValueError("IV_BUNDLE_ARCHIVE_RESEARCH_CONTRACT_MISMATCH")
    _reasons(value["reason_codes"])
    for name in ("first_pass", "second_pass"):
        observations = value[name]
        if not isinstance(observations, list) or len(observations) != len(requests):
            raise ValueError("IV_BUNDLE_ARCHIVE_COMPLETE_PASSES_REQUIRED")
        if len(canonical(observations).encode()) > 8388608 + 65:
            raise ValueError("IV_BUNDLE_ARCHIVE_PASS_BYTE_LIMIT")
        for request, observed in zip(requests, observations, strict=True):
            if (
                not isinstance(observed, dict)
                or set(observed) != REVALIDATION_FIELDS
                or observed["version"] != "research-iv-current-source-revalidation@1"
                or observed["build_id"] != request["build_id"]
                or observed["expected_archive_fingerprint"]
                != request["expected_archive_fingerprint"]
                or observed["status"] not in ("review_required", "matched_current_research_iv")
                or observed["canonical_contract_id"] is not None
                or any(observed[key] is not False for key in FLAGS & REVALIDATION_FIELDS)
                or any(
                    type(observed[key]) is not bool
                    for key in (
                        "archived_recording_verified",
                        "current_source_checked",
                        "exact_recording_reproduced",
                        "archive_unchanged_observed",
                    )
                )
            ):
                raise ValueError("IV_BUNDLE_ARCHIVE_OBSERVATION_CONTRACT_MISMATCH")
    if value["status"] == "review_required":
        if (
            value["bundle"] is not None
            or value["all_members_revalidated"] is not False
            or value["evidence_fingerprint"] is not None
        ):
            raise ValueError("IV_BUNDLE_ARCHIVE_REVIEW_CANNOT_CONTAIN_ACCEPTED_BUNDLE")
    elif value["status"] == "assembled_current_research_iv_bundle":
        _positive(value, requests)
    else:
        raise ValueError("IV_BUNDLE_ARCHIVE_RESULT_STATUS_UNSUPPORTED")
    return value


def _positive(value: dict[str, Any], requests: list[dict[str, str]]) -> None:
    from nse_quant.data_platform import research_iv_bundle as codec

    if codec.VERSION != "research-iv-feature-bundle@1":
        raise ValueError("IV_BUNDLE_ARCHIVE_CODEC_VERSION_UNSUPPORTED")
    manifest = value["bundle"]
    if not isinstance(manifest, dict) or "bundle_id" not in manifest:
        raise ValueError("IV_BUNDLE_ARCHIVE_BUNDLE_REQUIRED")
    manifest = dict(manifest)
    bundle_pin = manifest.pop("bundle_id")
    bundle = codec.decode_research_iv_bundle(
        canonical(manifest).encode(),
        expected_bundle_id=bundle_pin,
    )
    if (
        value["all_members_revalidated"] is not True
        or value["first_pass"] != value["second_pass"]
        or value["reason_codes"] != ["ALL_EXACT_MEMBERS_MATCHED_IN_TWO_FULL_PASSES"]
        or len(bundle.members) != len(requests)
    ):
        raise ValueError("IV_BUNDLE_ARCHIVE_POSITIVE_PASSES_MISMATCH")
    for request, observed, member in zip(
        requests,
        value["first_pass"],
        bundle.members,
        strict=True,
    ):
        if (
            observed["status"] != "matched_current_research_iv"
            or not pin(observed["evidence_fingerprint"])
            or any(
                observed[key] is not True
                for key in (
                    "archived_recording_verified",
                    "current_source_checked",
                    "exact_recording_reproduced",
                    "archive_unchanged_observed",
                )
            )
            or any(
                observed[key] is None
                for key in (
                    "archive_before",
                    "archive_after",
                    "fresh_before",
                    "fresh_after",
                    "comparison",
                )
            )
            or observed["archive_before"] != observed["archive_after"]
            or observed["fresh_before"] != observed["fresh_after"]
            or not isinstance(observed["comparison"], dict)
            or observed["comparison"]
            != {
                "recorded_matches_first": True,
                "recorded_matches_second": True,
                "fresh_observations_match": True,
                "all_observations_match": True,
                "reason_codes": [],
            }
            or (member.build_id, member.archive_fingerprint, member.revalidation_fingerprint)
            != (
                request["build_id"],
                request["expected_archive_fingerprint"],
                observed["evidence_fingerprint"],
            )
        ):
            raise ValueError("IV_BUNDLE_ARCHIVE_MEMBER_EVIDENCE_MISMATCH")
        archived, fresh = observed["archive_before"], observed["fresh_before"]
        if not isinstance(archived, dict) or not isinstance(fresh, dict):
            raise ValueError("IV_BUNDLE_ARCHIVE_NATIVE_OBJECTS_REQUIRED")
        revalidation_pin = sha(
            canonical(
                [
                    "research-iv-current-source-revalidation@1",
                    request["build_id"],
                    request["expected_archive_fingerprint"],
                    archived,
                    observed["archive_after"],
                    fresh,
                    observed["fresh_after"],
                    observed["comparison"],
                ]
            ).encode()
        )
        if (
            revalidation_pin != observed["evidence_fingerprint"]
            or archived.get("evidence_fingerprint") != request["expected_archive_fingerprint"]
            or archived.get("build_id") != request["build_id"]
            or archived.get("retained_head_build_id") != request["build_id"]
            or archived.get("status") != "verified_archived_head"
            or archived.get("recorded_result_status") != "research_iv_candidate"
            or archived.get("result_json") != canonical(fresh)
            or fresh.get("status") != "research_iv_candidate"
            or fresh.get("native_price_inputs_rechecked") is not True
        ):
            raise ValueError("IV_BUNDLE_ARCHIVE_REVALIDATION_CONTENT_MISMATCH")
        if (
            member.input_id != archived.get("input_id")
            or member.terms_json != archived.get("terms_json")
            or member.calculation_json != canonical(fresh.get("calculation"))
            or any(
                getattr(member, key) != fresh.get(key)
                for key in (
                    "option_build_id",
                    "spot_build_id",
                    "scenario_terms_sha256",
                    "source_option_event_ts",
                    "source_spot_event_ts",
                )
            )
        ):
            raise ValueError("IV_BUNDLE_ARCHIVE_MEMBER_PROJECTION_MISMATCH")
    expected = sha(
        canonical(
            [
                ASSEMBLY_VERSION,
                requests,
                value["first_pass"],
                value["second_pass"],
                bundle.bundle_id,
            ]
        ).encode()
    )
    if value["evidence_fingerprint"] != expected:
        raise ValueError("IV_BUNDLE_ARCHIVE_ASSEMBLY_FINGERPRINT_MISMATCH")


def record_id(scope: str, raw: str, requests_json: str) -> str:
    if not pin(scope):
        raise ValueError("IV_BUNDLE_ARCHIVE_SCOPE_PIN_REQUIRED")
    result_value(raw, requests_json)
    return sha(canonical([VERSION, scope, sha(raw.encode())]).encode())


def prior_links(raw: str, expected: tuple[str, ...]) -> None:
    if (
        type(expected) is not tuple
        or len(expected) > 256
        or any(not pin(x) for x in expected)
        or len(set(expected)) != len(expected)
        or checked(raw, MAX_LINK_BYTES) != list(expected)
    ):
        raise ValueError("IV_BUNDLE_ARCHIVE_ALL_PRIOR_LINKS_MISMATCH")
