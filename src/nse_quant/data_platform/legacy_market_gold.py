"""Versioned migrated-data Gold records from complete partition Silver content."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from nse_quant.data_platform import legacy_market_partition_silver as silver
from nse_quant.data_platform.legacy_market_gold_features import FEATURE_VERSION, price_geometry

VERSION = "legacy-market-price-gold@1"
MAX_ROWS = 16000
MAX_INPUT_ROW_BYTES = 524288
MAX_INPUT_TOTAL_BYTES = 33554432
MAX_FEATURE_ROW_BYTES = 65536
MAX_FEATURE_TOTAL_BYTES = 33554432
canonical = silver.canonical
sha = silver.sha
pin = silver.pin


class GoldRejected(ValueError):
    """Fixed refusal codes; operational source errors are not policy results."""


@dataclass(frozen=True)
class GoldSourcePins:
    revision_id: str
    recording_fingerprint: str

    def __post_init__(self) -> None:
        if not pin(self.revision_id) or not pin(self.recording_fingerprint):
            raise GoldRejected("EXACT_PARTITION_SILVER_GOLD_PINS_REQUIRED")

    @property
    def scope_id(self) -> str:
        # Fingerprint or runtime changes must not heal this source revision's obligation.
        return sha(canonical([VERSION, self.revision_id]))

    def arguments(self) -> dict[str, str]:
        return dict(
            revision_id=self.revision_id, expected_recording_fingerprint=self.recording_fingerprint
        )


DEFINITION = (
    VERSION,
    FEATURE_VERSION,
    "legacy-market-partition-silver@1",
    "one Gold feature row per complete source ordinal, no selection or salvage",
    "candle: high-low,close-open,high-max(open,close),min(open,close)-low",
    "option: ask-bid,(bid+ask)/2,ltp-midpoint,spot-strike",
    "exact reduced rational arithmetic on retained finite binary64, not provider decimal prices",
    "missing required operands yield UNAVAILABLE/null ratio, never zero imputation",
    "negative,zero,inverted,crossed,outside-range flags; no clipping or market approval",
    "source stored ts is event_ts only by explicit legacy-stored-time semantics",
    "no canonical identity,availability,economic validity,publication or decision admission",
    MAX_ROWS,
    MAX_INPUT_ROW_BYTES,
    MAX_INPUT_TOTAL_BYTES,
    MAX_FEATURE_ROW_BYTES,
    MAX_FEATURE_TOTAL_BYTES,
)


def checked_pins(pins: GoldSourcePins) -> GoldSourcePins:
    if type(pins) is not GoldSourcePins:
        raise GoldRejected("TYPED_GOLD_SOURCE_PINS_REQUIRED")
    return GoldSourcePins(**asdict(pins))


def validate_source_records(records: tuple[bytes, ...]) -> tuple[dict[str, Any], ...]:
    """Reconstruct/replay full native Silver content, not its audit attestation.

    The store MUST call the actual native reader. This function only establishes
    deterministic complete content equality for replay of retained Gold inputs.
    """
    if silver.VERSION != "legacy-market-partition-silver@1":
        raise GoldRejected("UNSUPPORTED_GOLD_SILVER_DEPENDENCY")
    if type(records) is not tuple or not 1 <= len(records) <= MAX_ROWS:
        raise GoldRejected("COMPLETE_GOLD_SOURCE_ROW_BOUND")
    total = 0
    for raw in records:
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_INPUT_ROW_BYTES:
            raise GoldRejected("GOLD_SOURCE_ROW_BYTE_BOUND")
        total += len(raw)
        if total > MAX_INPUT_TOTAL_BYTES:
            raise GoldRejected("GOLD_SOURCE_TOTAL_BYTE_BOUND")
    try:
        docs = tuple(json.loads(raw) for raw in records)
        pins = silver.PartitionBronzePins(**docs[0]["source_pins"])
        schema = silver.snapshot.SCHEMAS[pins.table]
        names = tuple(n for n, _kind in schema)
        rows = []
        for doc in docs:
            fields = doc["stored_fields"]
            if type(fields) is not dict or set(fields) != set(names):
                raise GoldRejected("EXACT_GOLD_SOURCE_FIELDS_REQUIRED")
            rows.append(tuple(fields[n] for n in names))
        capture = silver.partitions.make_partition_capture(
            table=pins.table, source_label=pins.source_label, schema=schema, rows=tuple(rows)
        )
        if capture.capture_id != pins.capture_id:
            raise GoldRejected("GOLD_SOURCE_COMPLETE_CAPTURE_MISMATCH")
        rebuilt = silver.derive_partition_records(capture.artifact, pins=pins)
        if rebuilt != records:
            raise GoldRejected("GOLD_SOURCE_FULL_SILVER_REPLAY_MISMATCH")
        return docs
    except GoldRejected:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
        raise GoldRejected("GOLD_SOURCE_CONTENT_CONTRACT") from None


def derive_gold_records(
    records: tuple[bytes, ...],
    *,
    pins: GoldSourcePins,
) -> tuple[bytes, ...]:
    """Complete pure recomputation; not native source verification or publication."""
    pins = checked_pins(pins)
    docs = validate_source_records(records)
    result: list[bytes] = []
    total = 0
    for raw, doc in zip(records, docs, strict=True):
        values = price_geometry(doc["stored_fields"], table=doc["source_table"])
        body = dict(
            version=VERSION,
            feature_version=FEATURE_VERSION,
            source_pins=asdict(pins),
            source_record_id=sha(raw),
            source_ordinal=doc["source_ordinal"],
            source_table=doc["source_table"],
            bronze_pins=doc["source_pins"],
            partition_index=doc["partition_index"],
            partition_ordinal=doc["partition_ordinal"],
            partition_payload_sha256=doc["partition_payload_sha256"],
            source_observation_id=doc["source_observation_id"],
            stored_key=doc["stored_key"],
            instrument_token=doc["stored_fields"]["instrument_token"],
            event_ts=doc["stored_fields"]["ts"],
            event_time_semantics="LEGACY_STORED_TS_NOT_INDEPENDENT_AVAILABILITY",
            native_recomputed_features=values["features"],
            quality_flags=values["quality_flags"],
            retained_legacy_derived_fields=doc["legacy_derived_fields"],
            classification="RECOMPUTED_RESEARCH_GEOMETRY_OVER_UNVALIDATED_LEGACY_VALUES",
            canonical_contract_id=None,
            independent_availability_verified=False,
            economic_validity_verified=False,
            published_at=None,
            publication_asserted=False,
            decision_eligibility_asserted=False,
        )
        encoded = canonical(body)
        total += len(encoded)
        if len(encoded) > MAX_FEATURE_ROW_BYTES or total > MAX_FEATURE_TOTAL_BYTES:
            raise GoldRejected("GOLD_FEATURE_BYTE_BOUND")
        result.append(encoded)
    return tuple(result)


def feature_values(raw: bytes) -> tuple[object, ...]:
    doc = json.loads(raw)
    return (
        doc["source_ordinal"],
        sha(raw),
        doc["source_record_id"],
        doc["source_table"],
        int(doc["instrument_token"]),
        datetime.fromisoformat(doc["event_ts"]),
        doc["feature_version"],
        None,
        raw,
    )
