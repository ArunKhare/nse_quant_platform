"""Audited Gold bundle combining the five completed per-table Gold recordings."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_daily_rv_gold as rv_gold
from nse_quant.data_platform import legacy_market_regimes_gold as regime_gold
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform import legacy_spot_candles_gold as candle_gold
from nse_quant.data_platform import legacy_spot_features_gold as feature_gold
from nse_quant.data_platform import legacy_underlying_iv_gold as iv_gold
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.legacy_spot_candles import Rejected, sha

VERSION = "legacy-market-gold-bundle-recording@1"
COMMAND = "persist.legacy_market_gold_bundle@1"
TABLE = "market_gold_bundle"
OBSERVATIONS = "market_gold_bundle_observations"
SETS = "market_gold_bundle_sets"
ATTEMPTS = "market_gold_bundle_attempts"
MAX_CONTEXT = 1048576
MEMBERS = (
    "spot_candles",
    "spot_features",
    "market_regimes",
    "underlying_iv",
    "daily_rv",
)
DEFINITION = (VERSION, COMMAND, "derived only from the five reviewed per-table Gold recordings")


def scope_id(source_label: str) -> str:
    return base.sha(base.canonical([VERSION, source_label]))


def initialize_market_gold_bundle(target: Any) -> None:
    AuditLedger(target).initialize()
    target.execute("CREATE SCHEMA IF NOT EXISTS gold")
    target.execute(
        f"CREATE TABLE IF NOT EXISTS gold.{SETS} ("
        "revision_id VARCHAR PRIMARY KEY,context BLOB NOT NULL,"
        "context_sha256 VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL)"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS gold.{OBSERVATIONS} ("
        "revision_id VARCHAR NOT NULL,member VARCHAR NOT NULL,ordinal BIGINT NOT NULL,"
        "record_bytes BLOB NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,"
        "PRIMARY KEY(revision_id,member,ordinal))"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS gold.{ATTEMPTS} ("
        "revision_id VARCHAR PRIMARY KEY,recorded_at TIMESTAMPTZ NOT NULL)"
    )


def observe_market_gold_bundle(
    gold_readers: dict[str, Any],
    *,
    pins: base.SilverPins,
    revision_ids: dict[str, str],
    gold_recording_fingerprints: dict[str, str],
) -> bytes:
    if not base.pin(pins.recording_fingerprint):
        raise Rejected("EXACT_MARKET_GOLD_BUNDLE_GOLD_PIN_REQUIRED")
    if (
        set(revision_ids) != set(MEMBERS)
        or set(gold_recording_fingerprints) != set(MEMBERS)
        or not all(base.pin(value) for value in revision_ids.values())
        or not all(base.pin(value) for value in gold_recording_fingerprints.values())
    ):
        raise Rejected("EXACT_MARKET_GOLD_BUNDLE_MEMBER_COVERAGE_REQUIRED")
    for reader in gold_readers.values():
        base.readonly(reader)
    candle_records = candle_gold.read_spot_candles_gold(
        gold_readers["spot_candles"],
        revision_id=revision_ids["spot_candles"],
        expected_recording_fingerprint=gold_recording_fingerprints["spot_candles"],
    )
    feature_records = feature_gold.read_spot_features_gold(
        gold_readers["spot_features"],
        revision_id=revision_ids["spot_features"],
        expected_recording_fingerprint=gold_recording_fingerprints["spot_features"],
    )
    regime_records = regime_gold.read_market_regimes_gold(
        gold_readers["market_regimes"],
        revision_id=revision_ids["market_regimes"],
        expected_recording_fingerprint=gold_recording_fingerprints["market_regimes"],
    )
    iv_records = iv_gold.read_underlying_iv_gold(
        gold_readers["underlying_iv"],
        revision_id=revision_ids["underlying_iv"],
        expected_recording_fingerprint=gold_recording_fingerprints["underlying_iv"],
    )
    rv_records = rv_gold.read_daily_rv_gold(
        gold_readers["daily_rv"],
        revision_id=revision_ids["daily_rv"],
        expected_recording_fingerprint=gold_recording_fingerprints["daily_rv"],
    )
    context = base.canonical(
        dict(
            version=VERSION,
            pins={
                "source_label": pins.source_label,
                "snapshot_id": pins.snapshot_id,
                "capture_event_id": pins.capture_event_id,
                "envelope_hash": pins.envelope_hash,
                "recording_fingerprint": pins.recording_fingerprint,
            },
            revision_ids=revision_ids,
            gold_recording_fingerprints=gold_recording_fingerprints,
            record_hashes={
                "spot_candles": [sha(record) for record in candle_records],
                "spot_features": [sha(record) for record in feature_records],
                "market_regimes": [sha(record) for record in regime_records],
                "underlying_iv": [sha(record) for record in iv_records],
                "daily_rv": [sha(record) for record in rv_records],
            },
        )
    )
    if len(context) > MAX_CONTEXT:
        raise Rejected("MARKET_GOLD_BUNDLE_CONTEXT_BOUND")
    return context


def persist_market_gold_bundle(
    gold_readers: dict[str, Any],
    target: Any,
    *,
    pins: base.SilverPins,
    revision_ids: dict[str, str],
    gold_recording_fingerprints: dict[str, str],
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    if (
        not base.pin(expected_context_sha256)
        or not base.actor(actor_id)
        or not base.revision(code_revision)
    ):
        raise Rejected("REVIEWED_MARKET_GOLD_BUNDLE_REQUEST_REQUIRED")
    for reader in gold_readers.values():
        base.separate(reader, target)
        base.readonly(reader)
    revision_id = base.sha(
        base.canonical(
            [
                VERSION,
                pins.recording_fingerprint,
                tuple(sorted(revision_ids.items())),
                tuple(sorted(gold_recording_fingerprints.items())),
                expected_context_sha256,
            ]
        )
    )
    for table, field in ((f"gold.{SETS}", "revision_id"), (f"gold.{ATTEMPTS}", "revision_id")):
        if target.execute(
            f"SELECT 1 FROM {table} WHERE {field}=? LIMIT 1", [revision_id]
        ).fetchone():
            raise Rejected("MARKET_GOLD_BUNDLE_FIRST_WRITE_ORIGINAL_OBLIGATION")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + scope_id(pins.source_label),
        config_hash=expected_context_sha256,
    )
    with ledger.execution(job):
        first = observe_market_gold_bundle(
            gold_readers,
            pins=pins,
            revision_ids=revision_ids,
            gold_recording_fingerprints=gold_recording_fingerprints,
        )
        if sha(first) != expected_context_sha256:
            raise Rejected("REVIEWED_MARKET_GOLD_BUNDLE_CONTEXT_CHANGED")
        second = observe_market_gold_bundle(
            gold_readers,
            pins=pins,
            revision_ids=revision_ids,
            gold_recording_fingerprints=gold_recording_fingerprints,
        )
        if second != first:
            raise Rejected("MARKET_GOLD_BUNDLE_CONTEXT_DRIFT")
        members = {
            "spot_candles": candle_gold.read_spot_candles_gold(
                gold_readers["spot_candles"],
                revision_id=revision_ids["spot_candles"],
                expected_recording_fingerprint=gold_recording_fingerprints["spot_candles"],
            ),
            "spot_features": feature_gold.read_spot_features_gold(
                gold_readers["spot_features"],
                revision_id=revision_ids["spot_features"],
                expected_recording_fingerprint=gold_recording_fingerprints["spot_features"],
            ),
            "market_regimes": regime_gold.read_market_regimes_gold(
                gold_readers["market_regimes"],
                revision_id=revision_ids["market_regimes"],
                expected_recording_fingerprint=gold_recording_fingerprints["market_regimes"],
            ),
            "underlying_iv": iv_gold.read_underlying_iv_gold(
                gold_readers["underlying_iv"],
                revision_id=revision_ids["underlying_iv"],
                expected_recording_fingerprint=gold_recording_fingerprints["underlying_iv"],
            ),
            "daily_rv": rv_gold.read_daily_rv_gold(
                gold_readers["daily_rv"],
                revision_id=revision_ids["daily_rv"],
                expected_recording_fingerprint=gold_recording_fingerprints["daily_rv"],
            ),
        }
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO gold.{SETS} VALUES (?,?,?,?)",
                [revision_id, first, expected_context_sha256, base.clock(datetime.now(UTC))],
            )
            for member, records in members.items():
                for ordinal, record in enumerate(records):
                    target.execute(
                        f"INSERT INTO gold.{OBSERVATIONS} VALUES (?,?,?,?,?)",
                        [revision_id, member, ordinal, record, base.clock(datetime.now(UTC))],
                    )
            target.execute(
                f"INSERT INTO gold.{ATTEMPTS} VALUES (?,?)",
                [revision_id, base.clock(datetime.now(UTC))],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    fingerprint, _ = _read_recording(target, revision_id=revision_id)
    return dict(
        revision_id=revision_id,
        recording_fingerprint=fingerprint,
        row_count=sum(len(records) for records in members.values()),
        job_id=job,
        decision_eligibility_asserted=False,
    )


def _read_recording(target: Any, *, revision_id: str) -> tuple[str, bytes]:
    if not base.pin(revision_id):
        raise Rejected("EXACT_MARKET_GOLD_BUNDLE_REVISION_PIN_REQUIRED")
    rows = base.metadata(
        target,
        f"SELECT CASE WHEN octet_length(context)<=? THEN context END,"
        f"CASE WHEN length(context_sha256)<=64 THEN context_sha256 END,recorded_at "
        f"FROM gold.{SETS} WHERE revision_id=?",
        [MAX_CONTEXT, revision_id],
        1,
    )
    context = bytes(rows[0][0])
    if rows[0][1] != sha(context):
        raise Rejected("MARKET_GOLD_BUNDLE_CONTEXT_HASH_MISMATCH")
    base.clock(rows[0][2])
    return sha(base.canonical([VERSION, revision_id, context.hex()])), context


def read_market_gold_bundle(
    reader: Any, *, revision_id: str, expected_recording_fingerprint: str
) -> dict[str, tuple[bytes, ...]]:
    if not base.pin(expected_recording_fingerprint):
        raise Rejected("EXACT_MARKET_GOLD_BUNDLE_RECORDING_PIN_REQUIRED")
    base.readonly(reader)
    fingerprint, context = _read_recording(reader, revision_id=revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise Rejected("MARKET_GOLD_BUNDLE_RECORDING_FINGERPRINT_CHANGED")
    rows = base.metadata(
        reader,
        "SELECT member,ordinal,"
        "CASE WHEN octet_length(record_bytes)<=1048576 THEN record_bytes END,"
        f"recorded_at FROM gold.{OBSERVATIONS} WHERE revision_id=? ORDER BY member,ordinal",
        [revision_id],
        -1,
    )
    members: dict[str, list[bytes]] = {name: [] for name in MEMBERS}
    for row in rows:
        if row[0] not in members:
            raise Rejected("MARKET_GOLD_BUNDLE_MEMBER_COVERAGE_MISMATCH")
        members[row[0]].append(bytes(row[2]))
    try:
        context_document = json.loads(context)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Rejected("MARKET_GOLD_BUNDLE_CONTEXT_RECORD_MISMATCH") from exc
    expected_hashes = {
        name: [sha(record) for record in records] for name, records in members.items()
    }
    if (
        not isinstance(context_document, dict)
        or set(context_document)
        != {
            "version",
            "pins",
            "revision_ids",
            "gold_recording_fingerprints",
            "record_hashes",
        }
        or context_document.get("version") != VERSION
        or context_document.get("record_hashes") != expected_hashes
        or base.canonical(context_document) != context
    ):
        raise Rejected("MARKET_GOLD_BUNDLE_CONTEXT_RECORD_MISMATCH")
    base.verify_recording(
        reader,
        command=COMMAND,
        scope_ref="sha256:" + scope_id(context_document["pins"]["source_label"]),
        config_hash=sha(context),
        revision_id=revision_id,
        sets_table=f"gold.{SETS}",
        observations_table=f"gold.{OBSERVATIONS}",
        attempts_table=f"gold.{ATTEMPTS}",
        observation_count=sum(len(records) for records in members.values()),
    )
    return {name: tuple(records) for name, records in members.items()}


def revalidate_market_gold_bundle(
    gold_readers: dict[str, Any], reader: Any, **args: Any
) -> dict[str, tuple[bytes, ...]]:
    for reader_item in gold_readers.values():
        base.separate(reader_item, reader)
    first = read_market_gold_bundle(
        reader,
        revision_id=args["revision_id"],
        expected_recording_fingerprint=args["expected_recording_fingerprint"],
    )
    pins = base.SilverPins(
        source_label=args.get("source_label", ""),
        snapshot_id=args.get("snapshot_id", ""),
        capture_event_id=args.get("capture_event_id", ""),
        envelope_hash=args.get("envelope_hash", ""),
        recording_fingerprint=args["recording_fingerprint"],
    )
    revision_ids = {
        "spot_candles": args["spot_candles_revision_id"],
        "spot_features": args["spot_features_revision_id"],
        "market_regimes": args["market_regimes_revision_id"],
        "underlying_iv": args["underlying_iv_revision_id"],
        "daily_rv": args["daily_rv_revision_id"],
    }
    context = observe_market_gold_bundle(
        gold_readers,
        pins=pins,
        revision_ids=revision_ids,
        gold_recording_fingerprints=args["gold_recording_fingerprints"],
    )
    _, recorded_context = _read_recording(reader, revision_id=args["revision_id"])
    if context != recorded_context:
        raise Rejected("MARKET_GOLD_BUNDLE_REVALIDATION_MISMATCH")
    return first
