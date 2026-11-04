"""Complete research bundle prerequisite; never publication or admission."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from nse_quant.data_platform import legacy_market_gold as gold
from nse_quant.data_platform import legacy_market_gold_store as store

VERSION = "legacy-price-research-bundle@1"
MAX_BYTES = 140_000_000


@dataclass(frozen=True)
class LegacyGoldBundleRequest:
    build_id: str
    recording_fingerprint: str

    def __post_init__(self) -> None:
        if not gold.pin(self.build_id) or not gold.pin(self.recording_fingerprint):
            raise ValueError("EXACT_LEGACY_BUNDLE_GOLD_PINS_REQUIRED")

    def arguments(self) -> dict[str, str]:
        return dict(
            build_id=self.build_id, expected_recording_fingerprint=self.recording_fingerprint
        )


def _encode(
    request: LegacyGoldBundleRequest,
    inputs: tuple[bytes, ...],
    outputs: tuple[bytes, ...],
    pins: gold.GoldSourcePins,
    runtime: bytes,
) -> bytes:
    expected = gold.derive_gold_records(inputs, pins=pins)
    if expected != outputs:
        raise ValueError("LEGACY_BUNDLE_FULL_RECOMPUTATION_MISMATCH")
    if store._build_id(pins, runtime, inputs, expected) != request.build_id:
        raise ValueError("LEGACY_BUNDLE_BUILD_CONTENT_MISMATCH")
    raw = gold.canonical(
        dict(
            version=VERSION,
            request=asdict(request),
            source_pins=asdict(pins),
            gold_definition=store._definition().hex(),
            runtime=runtime.hex(),
            inputs=[r.hex() for r in inputs],
            outputs=[r.hex() for r in outputs],
            purpose="RESEARCH_ONLY",
            publication_asserted=False,
            decision_eligibility_asserted=False,
            canonical_contract_id=None,
            availability_verified=False,
            economic_validity_verified=False,
            atomic_cross_database_snapshot_asserted=False,
        )
    )
    if len(raw) > MAX_BYTES:
        raise ValueError("LEGACY_BUNDLE_AGGREGATE_BYTE_BOUND")
    return raw


def replay_legacy_gold_bundle(raw: bytes, *, expected_bundle_id: str) -> bytes:
    """Full retained content recomputation, NOT native audit/source attestation.

    Recording fingerprint is retained as a declaration; offline content cannot
    independently establish that its original audit was successful.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("LEGACY_BUNDLE_BYTE_BOUND")
    if not gold.pin(expected_bundle_id) or gold.sha(raw) != expected_bundle_id:
        raise ValueError("LEGACY_BUNDLE_CHECKSUM")
    try:
        doc = json.loads(raw)
        request = LegacyGoldBundleRequest(**doc["request"])
        pins = gold.GoldSourcePins(**doc["source_pins"])
        # Bound encoded arrays BEFORE hex decoding or feature recomputation.
        for key, row_bound, total_bound in (
            ("inputs", gold.MAX_INPUT_ROW_BYTES, gold.MAX_INPUT_TOTAL_BYTES),
            ("outputs", gold.MAX_FEATURE_ROW_BYTES, gold.MAX_FEATURE_TOTAL_BYTES),
        ):
            rows = doc[key]
            if (
                type(rows) is not list
                or not 1 <= len(rows) <= gold.MAX_ROWS
                or any(type(r) is not str or not 0 < len(r) <= row_bound * 2 for r in rows)
                or sum(map(len, rows)) > total_bound * 2
            ):
                raise ValueError("LEGACY_BUNDLE_COMPONENT_BOUND")
        if (
            type(doc["runtime"]) is not str
            or len(doc["runtime"]) > 2048
            or doc["runtime"] != store._runtime().hex()
        ):
            raise ValueError("LEGACY_BUNDLE_EXACT_RUNTIME_REQUIRED")
        rebuilt = _encode(
            request,
            tuple(bytes.fromhex(r) for r in doc["inputs"]),
            tuple(bytes.fromhex(r) for r in doc["outputs"]),
            pins,
            bytes.fromhex(doc["runtime"]),
        )
        if rebuilt != raw:
            raise ValueError("LEGACY_BUNDLE_FULL_MANIFEST_MISMATCH")
    except (KeyError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise ValueError("LEGACY_BUNDLE_MALFORMED") from None
    return rebuilt


def assemble_legacy_gold_bundle(
    bronze: Any, silver: Any, recording: Any, *, request: LegacyGoldBundleRequest
) -> bytes:
    """Actual full native revalidation twice; no successful caller DTO import.

    One complete Gold build per bundle. No row selection, publication writes,
    inferred provider clocks, audit healing or positive eligibility.
    """
    if type(request) is not LegacyGoldBundleRequest:
        raise TypeError("TYPED_LEGACY_BUNDLE_REQUEST_REQUIRED")
    request = LegacyGoldBundleRequest(**asdict(request))
    first = store.revalidate_legacy_price_gold(bronze, silver, recording, **request.arguments())
    fingerprint, outputs, inputs, pins = store._recording(recording, request.build_id)
    if fingerprint != request.recording_fingerprint or first != outputs:
        raise ValueError("LEGACY_BUNDLE_RECORDING_DRIFT")
    raw = _encode(request, inputs, outputs, pins, store._runtime())
    second = store.revalidate_legacy_price_gold(bronze, silver, recording, **request.arguments())
    final_fingerprint, final_outputs, final_inputs, final_pins = store._recording(
        recording, request.build_id
    )
    if (
        second != first
        or final_fingerprint != fingerprint
        or final_outputs != outputs
        or final_inputs != inputs
        or final_pins != pins
    ):
        raise ValueError("LEGACY_BUNDLE_WHOLE_RECORDING_DRIFT")
    return raw


def revalidate_legacy_gold_bundle(
    bronze: Any, silver: Any, recording: Any, *, raw: bytes, expected_bundle_id: str
) -> bytes:
    """Offline replay followed by actual current Bronze/Silver/Gold comparison."""
    replay_legacy_gold_bundle(raw, expected_bundle_id=expected_bundle_id)
    request = LegacyGoldBundleRequest(**json.loads(raw)["request"])
    current = assemble_legacy_gold_bundle(bronze, silver, recording, request=request)
    if current != raw:
        raise ValueError("LEGACY_BUNDLE_CURRENT_NATIVE_MISMATCH")
    return current
