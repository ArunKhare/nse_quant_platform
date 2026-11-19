"""Bounded partition coverage for whole legacy tables; distinct from snapshot@1."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

VERSION = "legacy-market-partitions@1"
MAX_PARTITIONS = 16
ROWS_PER_PARTITION = 1000
MAX_ROWS = MAX_PARTITIONS * ROWS_PER_PARTITION
MAX_PART_BYTES = 1048576
MAX_ROW_TOTAL_BYTES = 4194304
MAX_ARTIFACT_BYTES = 16777216
KEYS = {"option_stream": (0, 1, 7), "spot_candles": (0, 2, 3)}


class PartitionRejected(ValueError):
    """Fixed refusal codes, never raw payload diagnostics."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


@dataclass(frozen=True)
class PartitionCapture:
    capture_id: str
    artifact: bytes
    manifest: bytes
    partitions: tuple[bytes, ...]
    row_count: int


def make_partition_capture(
    *,
    table: str,
    source_label: str,
    schema: tuple[tuple[str, str], ...],
    rows: tuple[tuple[object, ...], ...],
) -> PartitionCapture:
    """Pure exact-content constructor. Schema/cell semantics verified by native service.

    Key order is lexicographic canonical encoded legacy keys, NOT economic time.
    Schema is explicit retained metadata, not authority to introduce a native profile.
    """
    if (
        table not in KEYS
        or type(source_label) is not str
        or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", source_label) is None
        or type(schema) is not tuple
        or not 1 <= len(schema) <= 22
        or any(
            type(s) is not tuple
            or len(s) != 2
            or any(type(x) is not str or not 1 <= len(x) <= 64 for x in s)
            for s in schema
        )
        or len({s[0] for s in schema}) != len(schema)
    ):
        raise PartitionRejected("EXACT_SUPPORTED_TABLE_LABEL_SCHEMA_REQUIRED")
    if type(rows) is not tuple or not 1 <= len(rows) <= MAX_ROWS:
        raise PartitionRejected("WHOLE_TABLE_ROW_BOUND")
    keyed: list[tuple[bytes, tuple[object, ...]]] = []
    total = 0
    for row in rows:
        if (
            type(row) is not tuple
            or len(row) != len(schema)
            or any(x is not None and type(x) is not str for x in row)
            or any(isinstance(x, str) and len(x.encode()) > 65536 for x in row)
        ):
            raise PartitionRejected("EXACT_STORED_ROW_SHAPE_REQUIRED")
        if max(KEYS[table]) >= len(row) or any(row[i] is None for i in KEYS[table]):
            raise PartitionRejected("LEGACY_KEY_UNKNOWN")
        total += len(canonical(row))
        if total > MAX_ROW_TOTAL_BYTES:
            raise PartitionRejected("WHOLE_TABLE_ROW_BYTE_BOUND")
        keyed.append((canonical([row[i] for i in KEYS[table]]), row))
    keyed.sort(key=lambda item: item[0])
    if any(a[0] == b[0] for a, b in zip(keyed, keyed[1:], strict=False)):
        raise PartitionRejected("DUPLICATE_LEGACY_KEY_NO_WINNER")
    groups: list[list[tuple[bytes, tuple[object, ...]]]] = []
    group: list[tuple[bytes, tuple[object, ...]]] = []
    group_bytes = 0
    # Reserve bounded metadata overhead; exact payload is checked below as well.
    for item in keyed:
        size = len(canonical(item[1])) + 1
        if size > MAX_PART_BYTES - 4096:
            raise PartitionRejected("SINGLE_ROW_PARTITION_BYTE_BOUND")
        if group and (
            len(group) == ROWS_PER_PARTITION or group_bytes + size > MAX_PART_BYTES - 4096
        ):
            groups.append(group)
            group, group_bytes = [], 0
        group.append(item)
        group_bytes += size
    groups.append(group)
    if len(groups) > MAX_PARTITIONS:
        raise PartitionRejected("PARTITION_COUNT_BOUND")
    payloads: list[bytes] = []
    entries: list[dict[str, object]] = []
    ordinal = 0
    for index, items in enumerate(groups):
        raw = canonical(
            dict(
                version=VERSION,
                table=table,
                source_label=source_label,
                schema=schema,
                partition_index=index,
                first_ordinal=ordinal,
                lower_key_hex=items[0][0].hex(),
                upper_key_hex=items[-1][0].hex(),
                rows=[row for _key, row in items],
            )
        )
        if len(raw) > MAX_PART_BYTES:
            raise PartitionRejected("PARTITION_BYTE_BOUND")
        entries.append(
            dict(
                index=index,
                first_ordinal=ordinal,
                row_count=len(items),
                lower_key_hex=items[0][0].hex(),
                upper_key_hex=items[-1][0].hex(),
                payload_sha256=sha(raw),
                payload_bytes=len(raw),
            )
        )
        payloads.append(raw)
        ordinal += len(items)
    manifest = canonical(
        dict(
            version=VERSION,
            table=table,
            source_label=source_label,
            schema=schema,
            coverage="ENTIRE_SELECTED_TABLE_IN_ONE_SQL_SNAPSHOT",
            row_count=ordinal,
            partition_count=len(payloads),
            partitions=entries,
            row_sequence_sha256=sha(canonical([row for _key, row in keyed])),
            original_provider_bytes_retained=False,
            decision_eligibility_asserted=False,
        )
    )
    if len(manifest) > 65536:
        raise PartitionRejected("COVERAGE_MANIFEST_BYTE_BOUND")
    artifact = canonical(
        dict(
            version=VERSION,
            manifest_hex=manifest.hex(),
            partitions_hex=[raw.hex() for raw in payloads],
        )
    )
    if len(artifact) > MAX_ARTIFACT_BYTES:
        raise PartitionRejected("PARTITION_ARTIFACT_BYTE_BOUND")
    return PartitionCapture(sha(artifact), artifact, manifest, tuple(payloads), ordinal)


def replay_partition_capture(raw: bytes, *, expected_capture_id: str) -> PartitionCapture:
    """Rebuild complete coverage, ordering, partition boundaries and every retained byte."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_ARTIFACT_BYTES:
        raise PartitionRejected("PARTITION_ARTIFACT_BYTE_BOUND")
    if not pin(expected_capture_id) or sha(raw) != expected_capture_id:
        raise PartitionRejected("EXACT_PARTITION_CAPTURE_PIN_REQUIRED")
    try:
        envelope = json.loads(raw)
        if (
            type(envelope) is not dict
            or set(envelope) != {"version", "manifest_hex", "partitions_hex"}
            or canonical(envelope) != raw
            or envelope["version"] != VERSION
        ):
            raise PartitionRejected("CANONICAL_PARTITION_ENVELOPE_REQUIRED")
        text = envelope["manifest_hex"]
        if type(text) is not str or not 0 < len(text) <= 131072 or len(text) % 2:
            raise PartitionRejected("MANIFEST_HEX_BOUND")
        manifest_raw = bytes.fromhex(text)
        manifest = json.loads(manifest_raw)
        items = envelope["partitions_hex"]
        if type(items) is not list or not 1 <= len(items) <= MAX_PARTITIONS:
            raise PartitionRejected("PARTITION_COUNT_BOUND")
        rows: list[tuple[object, ...]] = []
        for item in items:
            if type(item) is not str or not 0 < len(item) <= MAX_PART_BYTES * 2 or len(item) % 2:
                raise PartitionRejected("PARTITION_HEX_BOUND")
            part = json.loads(bytes.fromhex(item))
            if type(part["rows"]) is not list or not 1 <= len(part["rows"]) <= ROWS_PER_PARTITION:
                raise PartitionRejected("PARTITION_ROW_BOUND")
            if any(type(row) is not list for row in part["rows"]):
                raise PartitionRejected("EXACT_STORED_ROW_SHAPE_REQUIRED")
            rows.extend(tuple(row) for row in part["rows"])
            if len(rows) > MAX_ROWS:
                raise PartitionRejected("WHOLE_TABLE_ROW_BOUND")
        rebuilt = make_partition_capture(
            table=manifest["table"],
            source_label=manifest["source_label"],
            schema=tuple(tuple(s) for s in manifest["schema"]),
            rows=tuple(rows),
        )
        if rebuilt.artifact != raw:
            raise PartitionRejected("COMPLETE_PARTITION_COVERAGE_REPLAY_MISMATCH")
        return rebuilt
    except PartitionRejected:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
        raise PartitionRejected("MALFORMED_PARTITION_CAPTURE") from None


def capture_partitioned_legacy_table(
    source: Any,
    *,
    table: str,
    source_label: str,
) -> PartitionCapture:
    """Actual read-only whole-table capture, not independent OFFSET queries or views."""
    from nse_quant.data_platform import legacy_market_snapshot as native

    if (
        native.VERSION != "legacy-market-snapshot@1"
        or native.KEYS != KEYS
        or table not in native.SCHEMAS
    ):
        raise PartitionRejected("UNSUPPORTED_LEGACY_CAPTURE_DEPENDENCY")
    if type(source_label) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", source_label) is None:
        raise PartitionRejected("EXACT_SUPPORTED_TABLE_LABEL_SCHEMA_REQUIRED")
    if source.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise PartitionRejected("READONLY_LEGACY_SOURCE_REQUIRED")
    target = native._name(source, "main", table)
    schema = native.SCHEMAS[table]
    source.execute("BEGIN TRANSACTION")
    try:
        stored = source.execute(
            "SELECT column_name,data_type FROM information_schema.columns "
            "WHERE table_catalog=current_database() AND table_schema='main' AND table_name=? "
            "ORDER BY ordinal_position LIMIT 24",
            [table],
        ).fetchall()
        kinds = source.execute(
            "SELECT table_type FROM information_schema.tables WHERE table_catalog="
            "current_database() AND table_schema='main' AND table_name=?",
            [table],
        ).fetchall()
        if tuple(stored) != schema or kinds != [("BASE TABLE",)]:
            raise PartitionRejected("EXACT_LEGACY_BASE_TABLE_SCHEMA_REQUIRED")
        guards = " OR ".join(
            f"octet_length(encode(CAST({native._quote(n)} AS VARCHAR)))>{native.MAX_CELL}"
            for n, t in schema
            if t in ("VARCHAR", "JSON")
        )
        if source.execute(f"SELECT 1 FROM {target} WHERE {guards} LIMIT 1").fetchone():
            raise PartitionRejected("TEXT_CELL_BOUND")
        columns = ",".join(native._quote(n) for n, _t in schema)
        cursor = source.execute(f"SELECT {columns} FROM {target} LIMIT {MAX_ROWS + 1}")
        rows: list[tuple[object, ...]] = []
        total_bytes = 0
        while True:
            batch = cursor.fetchmany(128)
            if not batch:
                break
            for row in batch:
                encoded = tuple(
                    native._cell(value, kind) for value, (_n, kind) in zip(row, schema, strict=True)
                )
                total_bytes += len(canonical(encoded))
                if total_bytes > MAX_ROW_TOTAL_BYTES:
                    raise PartitionRejected("WHOLE_TABLE_ROW_BYTE_BOUND")
                rows.append(encoded)
                if len(rows) > MAX_ROWS:
                    raise PartitionRejected("WHOLE_TABLE_ROW_BOUND")
        result = make_partition_capture(
            table=table, source_label=source_label, schema=schema, rows=tuple(rows)
        )
        source.execute("COMMIT")
        return result
    except BaseException:
        source.execute("ROLLBACK")
        raise
