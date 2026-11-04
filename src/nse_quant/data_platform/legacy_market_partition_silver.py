"""Exact partition-aware Silver projection; pure replay is not source attestation."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from nse_quant.data_platform import legacy_market_partitions as partitions
from nse_quant.data_platform import legacy_market_silver as cells
from nse_quant.data_platform import legacy_market_snapshot as snapshot

VERSION = "legacy-market-partition-silver@1"
MAX_RECORD_BYTES = 524288
MAX_RECORD_TOTAL_BYTES = 33554432
MAX_CONTEXT_BYTES = partitions.MAX_ARTIFACT_BYTES
canonical = partitions.canonical
sha = partitions.sha
pin = partitions.pin


class PartitionSilverRejected(ValueError):
    """Fixed refusal codes; operational SQL errors propagate."""


@dataclass(frozen=True)
class PartitionBronzePins:
    capture_id: str
    table: str
    source_label: str
    recording_fingerprint: str

    def __post_init__(self) -> None:
        if (
            not pin(self.capture_id)
            or not pin(self.recording_fingerprint)
            or type(self.table) is not str
            or self.table not in partitions.KEYS
            or type(self.source_label) is not str
            or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.source_label) is None
        ):
            raise PartitionSilverRejected("EXACT_PARTITION_BRONZE_PINS_REQUIRED")

    @property
    def scope_id(self) -> str:
        # Recording metadata drift must not create a fresh adoptable scope.
        return sha(canonical([VERSION, self.capture_id, self.table, self.source_label]))

    def reader_arguments(self) -> dict[str, str]:
        return dict(
            capture_id=self.capture_id,
            table=self.table,
            source_label=self.source_label,
            expected_recording_fingerprint=self.recording_fingerprint,
        )


DEFINITION = (
    VERSION,
    "legacy-market-partitions@1",
    "legacy-market-silver@1 exact scalar validator only; not snapshot projection",
    "complete artifact replay, capture/partition/local/global lineage, full scalar equality",
    MAX_CONTEXT_BYTES,
    MAX_RECORD_BYTES,
    MAX_RECORD_TOTAL_BYTES,
    partitions.MAX_ROWS,
    partitions.MAX_PARTITIONS,
    "legacy-derived analytics are not recomputed; no identity/time/decision admission",
)


def checked_pins(pins: PartitionBronzePins) -> PartitionBronzePins:
    if type(pins) is not PartitionBronzePins:
        raise PartitionSilverRejected("TYPED_PARTITION_PINS_REQUIRED")
    return PartitionBronzePins(**asdict(pins))


def derive_partition_records(artifact: bytes, *, pins: PartitionBronzePins) -> tuple[bytes, ...]:
    """Untrusted content validation only; native producer must read actual Bronze."""
    pins = checked_pins(pins)
    if (
        partitions.VERSION != "legacy-market-partitions@1"
        or snapshot.VERSION != "legacy-market-snapshot@1"
        or cells.VERSION != "legacy-market-silver@1"
    ):
        raise PartitionSilverRejected("UNSUPPORTED_PARTITION_SILVER_DEPENDENCY")
    capture = partitions.replay_partition_capture(artifact, expected_capture_id=pins.capture_id)
    manifest = json.loads(capture.manifest)
    if (
        manifest["table"] != pins.table
        or manifest["source_label"] != pins.source_label
        or manifest["schema"] != [list(s) for s in snapshot.SCHEMAS[pins.table]]
    ):
        raise PartitionSilverRejected("EXACT_PARTITION_SUBJECT_SCHEMA_REQUIRED")
    names = tuple(n for n, _kind in snapshot.SCHEMAS[pins.table])
    scope = sha(canonical([partitions.VERSION, pins.table, pins.source_label, pins.capture_id]))
    output: list[bytes] = []
    total = 0
    try:
        for index, payload in enumerate(capture.partitions):
            part = json.loads(payload)
            entry = manifest["partitions"][index]
            event_id = sha(
                canonical(["legacy_market_partition_capture", scope, f"part-{index:04d}"])
            )
            for local, row in enumerate(part["rows"]):
                fields = dict(zip(names, row, strict=True))
                cells._validate_cells(fields)
                if fields["instrument_token"] is None or fields["ts"] is None:
                    raise PartitionSilverRejected("MATERIALIZED_TOKEN_AND_STORED_TIME_REQUIRED")
                raw = canonical(
                    dict(
                        version=VERSION,
                        source_pins=asdict(pins),
                        source_table=pins.table,
                        source_ordinal=len(output),
                        partition_index=index,
                        partition_ordinal=local,
                        partition_payload_sha256=sha(payload),
                        partition_first_ordinal=entry["first_ordinal"],
                        partition_lower_key_hex=entry["lower_key_hex"],
                        partition_upper_key_hex=entry["upper_key_hex"],
                        source_observation_id=event_id,
                        stored_key=[row[i] for i in partitions.KEYS[pins.table]],
                        stored_fields=fields,
                        legacy_derived_fields={
                            k: v for k, v in fields.items() if k in cells.DERIVED
                        },
                        classification="RETAINED_LEGACY_OBSERVATION_NOT_MARKET_VALIDATED",
                        source_time_semantics="LEGACY_STORED_TS_NOT_INDEPENDENT_AVAILABILITY",
                        original_provider_bytes_retained=False,
                        canonical_contract_id=None,
                        identity_verified=False,
                        availability_evidence_verified=False,
                        economic_validity_verified=False,
                        publication_asserted=False,
                        decision_eligibility_asserted=False,
                    )
                )
                total += len(raw)
                if len(raw) > MAX_RECORD_BYTES or total > MAX_RECORD_TOTAL_BYTES:
                    raise PartitionSilverRejected("PARTITION_SILVER_RECORD_BYTE_BOUND")
                output.append(raw)
        if len(output) != capture.row_count:
            raise PartitionSilverRejected("PARTITION_SILVER_COMPLETE_COUNT_MISMATCH")
        return tuple(output)
    except PartitionSilverRejected:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise PartitionSilverRejected("PARTITION_SILVER_STORED_VALUE_CONTRACT") from None


def record_values(raw: bytes) -> tuple[object, ...]:
    """All materialized SQL indices, recomputed from complete expected record bytes."""
    body: dict[str, Any] = json.loads(raw)
    fields = body["stored_fields"]
    return (
        body["source_ordinal"],
        body["partition_index"],
        body["partition_ordinal"],
        body["partition_payload_sha256"],
        sha(raw),
        body["source_table"],
        int(fields["instrument_token"]),
        datetime.fromisoformat(fields["ts"]),
        None if fields["volume"] is None else int(fields["volume"]),
        None if fields["oi"] is None else int(fields["oi"]),
        raw,
        body["source_observation_id"],
        body["source_pins"]["capture_id"],
    )
