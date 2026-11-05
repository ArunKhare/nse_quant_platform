"""Complete native return-window research bundles; content integrity is not authority."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from nse_quant.data_platform import legacy_return_window_store as source

VERSION = "legacy-window-research-bundle@1"
MAX_BYTES = 140000000
MAX_ROWS = 16000
canonical = source.canonical
sha = source.sha
pin = source.source.source.codec.pin


@dataclass(frozen=True)
class WindowBundleRequest:
    build_id: str
    recording_fingerprint: str

    def __post_init__(self) -> None:
        if not pin(self.build_id) or not pin(self.recording_fingerprint):
            raise ValueError("EXACT_WINDOW_BUNDLE_RECORDING_PINS_REQUIRED")

    def arguments(self) -> dict[str, str]:
        return dict(
            build_id=self.build_id, expected_recording_fingerprint=self.recording_fingerprint
        )


def _encode(
    request: WindowBundleRequest,
    context: bytes,
    inputs: tuple[bytes, ...],
    outputs: tuple[bytes, ...],
    pins: source.ReturnWindowPins,
    policy: source.features.ReturnWindowPolicy,
) -> bytes:
    expected = source._recompute(context, inputs, pins, policy)
    if outputs != expected or source._id(pins, policy, context, expected) != request.build_id:
        raise ValueError("WINDOW_BUNDLE_COMPLETE_SOURCE_CONTENT_MISMATCH")
    raw = canonical(
        dict(
            version=VERSION,
            request=asdict(request),
            source_definition=source._definition().hex(),
            source_pins=asdict(pins),
            policy=asdict(policy),
            context=context.hex(),
            inputs=[r.hex() for r in inputs],
            outputs=[r.hex() for r in outputs],
            purpose="RESEARCH_ONLY",
            canonical_contract_id=None,
            independent_availability_verified=False,
            economic_validity_verified=False,
            authoritative_market_coverage_verified=False,
            publication_asserted=False,
            decision_eligibility_asserted=False,
            atomic_cross_database_snapshot_asserted=False,
        )
    )
    if len(raw) > MAX_BYTES:
        raise ValueError("WINDOW_BUNDLE_AGGREGATE_BYTE_BOUND")
    return raw


def replay_window_bundle(raw: bytes, *, expected_bundle_id: str) -> bytes:
    """Complete offline recomputation, not independent original recording/audit attestation."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("WINDOW_BUNDLE_BYTE_BOUND")
    if not pin(expected_bundle_id) or sha(raw) != expected_bundle_id:
        raise ValueError("WINDOW_BUNDLE_CHECKSUM")
    try:
        doc = json.loads(raw)
        request = WindowBundleRequest(**doc["request"])
        pins = source.ReturnWindowPins(**doc["source_pins"])
        policy = source.features.ReturnWindowPolicy(**doc["policy"])
        encoded_context = doc["context"]
        if (
            type(encoded_context) is not str
            or not 0 < len(encoded_context) <= 2 * source.MAX_CONTEXT_BYTES
        ):
            raise ValueError("WINDOW_BUNDLE_CONTEXT_BOUND")
        for key, row_limit, total_limit in (
            (
                "inputs",
                source.source.source.codec.MAX_INPUT_ROW_BYTES,
                source.source.source.codec.MAX_INPUT_TOTAL_BYTES,
            ),
            ("outputs", source.features.MAX_ROW_BYTES, source.features.MAX_TOTAL_BYTES),
        ):
            rows = doc[key]
            if (
                type(rows) is not list
                or not 1 <= len(rows) <= MAX_ROWS
                or any(type(r) is not str or not 0 < len(r) <= row_limit * 2 for r in rows)
                or sum(map(len, rows)) > total_limit * 2
            ):
                raise ValueError("WINDOW_BUNDLE_COMPONENT_BYTE_OR_COUNT_BOUND")
        rebuilt = _encode(
            request,
            bytes.fromhex(encoded_context),
            tuple(bytes.fromhex(r) for r in doc["inputs"]),
            tuple(bytes.fromhex(r) for r in doc["outputs"]),
            pins,
            policy,
        )
        if rebuilt != raw:
            raise ValueError("WINDOW_BUNDLE_FULL_CANONICAL_MANIFEST_MISMATCH")
    except (KeyError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise ValueError("WINDOW_BUNDLE_MALFORMED") from None
    return rebuilt


def _observe(
    bronze: Any,
    silver: Any,
    geometry: Any,
    returns: Any,
    windows: Any,
    request: WindowBundleRequest,
) -> tuple[
    bytes,
    tuple[bytes, ...],
    tuple[bytes, ...],
    source.ReturnWindowPins,
    source.features.ReturnWindowPolicy,
]:
    first = source.revalidate_return_window_gold(
        bronze, silver, geometry, returns, windows, **request.arguments()
    )
    fingerprint, rows, inputs, pins, policy = source._recording(windows, request.build_id)
    context = windows.execute(
        f"SELECT CASE WHEN octet_length(context)<=? THEN context END "
        f"FROM {source.name(windows, 'gold', source.DOMAIN[1])} WHERE build_id=?",
        [source.MAX_CONTEXT_BYTES, request.build_id],
    ).fetchone()
    if (
        fingerprint != request.recording_fingerprint
        or first != rows
        or context is None
        or context[0] is None
    ):
        raise ValueError("WINDOW_BUNDLE_ORIGINAL_RECORDING_DRIFT")
    return bytes(context[0]), inputs, rows, pins, policy


def assemble_window_bundle(
    bronze: Any,
    silver: Any,
    geometry: Any,
    returns: Any,
    windows: Any,
    *,
    request: WindowBundleRequest,
) -> bytes:
    """Actual pinned full native observations twice; no successful caller-DTO import."""
    if type(request) is not WindowBundleRequest:
        raise TypeError("TYPED_WINDOW_BUNDLE_REQUEST_REQUIRED")
    request = WindowBundleRequest(**asdict(request))
    first = _observe(bronze, silver, geometry, returns, windows, request)
    raw = _encode(request, *first)
    second = _observe(bronze, silver, geometry, returns, windows, request)
    if first != second:
        raise ValueError("WINDOW_BUNDLE_COMPLETE_NATIVE_OBSERVATION_DRIFT")
    return raw


def revalidate_window_bundle(
    bronze: Any,
    silver: Any,
    geometry: Any,
    returns: Any,
    windows: Any,
    *,
    raw: bytes,
    expected_bundle_id: str,
) -> bytes:
    replay_window_bundle(raw, expected_bundle_id=expected_bundle_id)
    request = WindowBundleRequest(**json.loads(raw)["request"])
    current = assemble_window_bundle(bronze, silver, geometry, returns, windows, request=request)
    if current != raw:
        raise ValueError("WINDOW_BUNDLE_CURRENT_NATIVE_SOURCE_MISMATCH")
    return raw
