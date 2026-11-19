"""Build Silver option-stream observations from a dedicated Medallion Bronze database.

Safety:
- Reads only Bronze.
- Writes only to a dedicated Silver database.
- Historical import lineage only.
- No live acquisition, trading, decision eligibility, or production cutover.
- Idempotent by Bronze snapshot identity and Silver revision identity.
- Preserves missing values; does not fill, interpolate, or repair data.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.data_platform.native_option_chain_snapshot import (
    canonical,
    json_safe,
    sha,
)

SILVER_COMMAND = "normalize.legacy_option_stream_silver@1"
SILVER_VERSION = "legacy-option-stream-silver@1"
BRONZE_PAYLOAD_FORMAT = "legacy-option-stream-snapshot@1"

SILVER_DDL = """
CREATE SCHEMA IF NOT EXISTS silver;
CREATE TABLE IF NOT EXISTS silver.option_stream_observations (
    revision_id VARCHAR NOT NULL,
    source_ordinal BIGINT NOT NULL,
    bronze_snapshot_id VARCHAR NOT NULL,
    bronze_capture_event_id VARCHAR NOT NULL,
    bronze_envelope_hash VARCHAR NOT NULL,
    bronze_recording_fingerprint VARCHAR NOT NULL,
    bronze_source_label VARCHAR NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    underlying VARCHAR NOT NULL,
    expiry DATE,
    strike DOUBLE,
    option_type VARCHAR,
    tradingsymbol VARCHAR,
    instrument_token BIGINT,
    lot_size BIGINT,
    spot DOUBLE,
    ltp DOUBLE,
    bid DOUBLE,
    ask DOUBLE,
    volume BIGINT,
    oi BIGINT,
    iv DOUBLE,
    delta DOUBLE,
    gamma DOUBLE,
    vega DOUBLE,
    theta DOUBLE,
    quote_status VARCHAR,
    payload_json VARCHAR,
    quality_status VARCHAR NOT NULL,
    quality_reason VARCHAR,
    recorded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (revision_id, source_ordinal)
);
CREATE TABLE IF NOT EXISTS silver.option_stream_revisions (
    revision_id VARCHAR PRIMARY KEY,
    bronze_snapshot_id VARCHAR NOT NULL,
    bronze_capture_event_id VARCHAR NOT NULL,
    bronze_envelope_hash VARCHAR NOT NULL,
    bronze_recording_fingerprint VARCHAR NOT NULL,
    bronze_source_label VARCHAR NOT NULL,
    context_sha256 VARCHAR NOT NULL,
    observation_count BIGINT NOT NULL,
    quarantined_count BIGINT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);
"""


def ensure_silver(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(SILVER_DDL)


def bronze_snapshot_ids(
    bronze_conn: duckdb.DuckDBPyConnection,
    *,
    underlying: str,
    start_date: date,
    end_date: date,
) -> list[tuple[str, str, str, str, str]]:
    rows = bronze_conn.execute(
        """
        SELECT
            json_extract_string(decode(payload), '$.source_label') AS source_label,
            sha256(payload) AS snapshot_id,
            capture_event_id,
            envelope_hash,
            payload_hash
        FROM bronze.event_variants
        WHERE origin_kind = 'historical_import'
          AND payload_format = ?
          AND source = 'legacy_option_stream_historical_import'
          AND json_extract_string(decode(payload), '$.snapshot.underlying') = ?
          AND received_at >= ?
          AND received_at < ?
        ORDER BY received_at
        """,
        [
            BRONZE_PAYLOAD_FORMAT,
            underlying,
            datetime.combine(start_date, datetime.min.time()).isoformat(),
            (datetime.combine(end_date, datetime.min.time()) + timedelta(days=1)).isoformat(),
        ],
    ).fetchall()
    return [(row[0], row[1], row[2], row[3], row[4]) for row in rows]


def read_bronze_payload(
    bronze_conn: duckdb.DuckDBPyConnection,
    *,
    source_label: str,
    snapshot_id: str,
    capture_event_id: str,
    envelope_hash: str,
) -> bytes:
    rows = bronze_conn.execute(
        """
        SELECT payload, payload_hash
        FROM bronze.event_variants
        WHERE capture_event_id = ?
          AND envelope_hash = ?
        LIMIT 2
        """,
        [capture_event_id, envelope_hash],
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("Expected exactly one Bronze variant for snapshot pins")
    payload = bytes(rows[0][0])
    if sha(payload) != snapshot_id or sha(payload) != rows[0][1]:
        raise ValueError("Bronze payload hash does not match snapshot pins")
    decoded = json.loads(payload)
    if decoded.get("source_label") != source_label:
        raise ValueError("Bronze payload source label does not match requested source label")
    return payload


def normalize_row(
    row: dict[str, Any],
    *,
    source_ordinal: int,
    snapshot_ts: datetime,
    underlying: str,
) -> tuple[dict[str, Any], str | None]:
    def optional_float(key: str) -> float | None:
        value = row.get(key)
        if value is None:
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        if result != result or result in (float("inf"), float("-inf")):
            return None
        return result

    def optional_int(key: str) -> int | None:
        value = row.get(key)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def optional_text(key: str) -> str | None:
        value = row.get(key)
        return str(value) if value is not None else None

    expiry = row.get("expiry")
    if isinstance(expiry, datetime):
        expiry_date = expiry.date()
    elif isinstance(expiry, date):
        expiry_date = expiry
    else:
        expiry_date = None

    observation: dict[str, Any] = {
        "source_ordinal": source_ordinal,
        "ts": snapshot_ts,
        "underlying": underlying,
        "expiry": expiry_date,
        "strike": optional_float("strike"),
        "option_type": optional_text("option_type"),
        "tradingsymbol": optional_text("tradingsymbol"),
        "instrument_token": optional_int("instrument_token"),
        "lot_size": optional_int("lot_size"),
        "spot": optional_float("spot"),
        "ltp": optional_float("ltp"),
        "bid": optional_float("bid"),
        "ask": optional_float("ask"),
        "volume": optional_int("volume"),
        "oi": optional_int("oi"),
        "iv": optional_float("iv"),
        "delta": optional_float("delta"),
        "gamma": optional_float("gamma"),
        "vega": optional_float("vega"),
        "theta": optional_float("theta"),
        "quote_status": optional_text("quote_status"),
        "payload_json": optional_text("payload_json"),
    }

    option_type = observation["option_type"]
    if option_type is not None and option_type not in {"CE", "PE"}:
        return observation, "INVALID_OPTION_TYPE"
    strike = observation["strike"]
    if strike is not None and strike < 0:
        return observation, "NEGATIVE_STRIKE"
    spot = observation["spot"]
    if spot is not None and spot <= 0:
        return observation, "NON_POSITIVE_SPOT"
    ltp = observation["ltp"]
    bid = observation["bid"]
    ask = observation["ask"]
    if (ltp is not None and ltp < 0) or (bid is not None and bid < 0) or (ask is not None and ask < 0):
        return observation, "NEGATIVE_PRICE"
    volume = observation["volume"]
    oi = observation["oi"]
    if (volume is not None and volume < 0) or (oi is not None and oi < 0):
        return observation, "NEGATIVE_VOLUME_OR_OI"
    return observation, None


def revision_id_for(
    *,
    snapshot_id: str,
    capture_event_id: str,
    envelope_hash: str,
    recording_fingerprint: str,
) -> str:
    return sha(
        canonical(
            [
                SILVER_VERSION,
                SILVER_COMMAND,
                snapshot_id,
                capture_event_id,
                envelope_hash,
                recording_fingerprint,
            ]
        )
    )


def already_built(
    silver_conn: duckdb.DuckDBPyConnection,
    *,
    revision_id: str,
) -> bool:
    row = silver_conn.execute(
        "SELECT 1 FROM silver.option_stream_revisions WHERE revision_id = ?",
        [revision_id],
    ).fetchone()
    return row is not None


def build_silver_snapshot(
    bronze_conn: duckdb.DuckDBPyConnection,
    silver_conn: duckdb.DuckDBPyConnection,
    *,
    source_label: str,
    snapshot_id: str,
    capture_event_id: str,
    envelope_hash: str,
    recording_fingerprint: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    revision_id = revision_id_for(
        snapshot_id=snapshot_id,
        capture_event_id=capture_event_id,
        envelope_hash=envelope_hash,
        recording_fingerprint=recording_fingerprint,
    )
    if already_built(silver_conn, revision_id=revision_id):
        return {"revision_id": revision_id, "status": "SKIPPED"}

    payload = read_bronze_payload(
        bronze_conn,
        source_label=source_label,
        snapshot_id=snapshot_id,
        capture_event_id=capture_event_id,
        envelope_hash=envelope_hash,
    )
    document = json.loads(payload)
    snapshot = document["snapshot"]
    snapshot_ts = datetime.fromisoformat(snapshot["snapshot_ts"])
    underlying = snapshot["underlying"]
    rows = snapshot["rows"]

    observations: list[tuple[Any, ...]] = []
    quarantined = 0
    for ordinal, row in enumerate(rows):
        observation, reason = normalize_row(
            row,
            source_ordinal=ordinal,
            snapshot_ts=snapshot_ts,
            underlying=underlying,
        )
        quality_status = "QUARANTINED" if reason else "VALID"
        quarantined += int(reason is not None)
        observations.append(
            (
                revision_id,
                observation["source_ordinal"],
                snapshot_id,
                capture_event_id,
                envelope_hash,
                recording_fingerprint,
                source_label,
                observation["ts"],
                observation["underlying"],
                observation["expiry"],
                observation["strike"],
                observation["option_type"],
                observation["tradingsymbol"],
                observation["instrument_token"],
                observation["lot_size"],
                observation["spot"],
                observation["ltp"],
                observation["bid"],
                observation["ask"],
                observation["volume"],
                observation["oi"],
                observation["iv"],
                observation["delta"],
                observation["gamma"],
                observation["vega"],
                observation["theta"],
                observation["quote_status"],
                observation["payload_json"],
                quality_status,
                reason,
                datetime.now(UTC),
            )
        )

    context = canonical(
        json_safe(
            {
                "version": SILVER_VERSION,
                "command": SILVER_COMMAND,
                "bronze_pins": {
                    "source_label": source_label,
                    "snapshot_id": snapshot_id,
                    "capture_event_id": capture_event_id,
                    "envelope_hash": envelope_hash,
                    "recording_fingerprint": recording_fingerprint,
                },
                "observation_count": len(rows),
                "quarantined_count": quarantined,
            }
        )
    )
    context_hash = sha(context)

    silver_conn.execute("BEGIN TRANSACTION")
    try:
        silver_conn.execute(
            """
            INSERT INTO silver.option_stream_revisions (
                revision_id, bronze_snapshot_id, bronze_capture_event_id,
                bronze_envelope_hash, bronze_recording_fingerprint,
                bronze_source_label, context_sha256, observation_count,
                quarantined_count, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                revision_id,
                snapshot_id,
                capture_event_id,
                envelope_hash,
                recording_fingerprint,
                source_label,
                context_hash,
                len(rows),
                quarantined,
                datetime.now(UTC),
            ],
        )
        silver_conn.executemany(
            """
            INSERT INTO silver.option_stream_observations (
                revision_id, source_ordinal, bronze_snapshot_id,
                bronze_capture_event_id, bronze_envelope_hash,
                bronze_recording_fingerprint, bronze_source_label,
                ts, underlying, expiry, strike, option_type, tradingsymbol,
                instrument_token, lot_size, spot, ltp, bid, ask, volume, oi,
                iv, delta, gamma, vega, theta, quote_status, payload_json,
                quality_status, quality_reason, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            observations,
        )
        silver_conn.execute("COMMIT")
    except BaseException:
        silver_conn.execute("ROLLBACK")
        raise

    return {
        "revision_id": revision_id,
        "status": "BUILT",
        "observation_count": len(rows),
        "quarantined_count": quarantined,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-db", type=Path, required=True)
    parser.add_argument("--silver-db", type=Path, required=True)
    parser.add_argument("--underlying", default="NIFTY")
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--actor-id", default="silver-builder")
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--mode", choices=["dry-run", "apply"], default="dry-run")
    args = parser.parse_args()

    if args.start_date > args.end_date:
        raise ValueError("--start-date must be <= --end-date")
    if args.bronze_db.resolve() == args.silver_db.resolve():
        raise ValueError("--bronze-db and --silver-db must be different files")

    bronze_conn = duckdb.connect(str(args.bronze_db), read_only=True)
    silver_conn = duckdb.connect(str(args.silver_db))
    try:
        BronzeEventStore(bronze_conn).verify_target()
        ensure_silver(silver_conn)
        snapshots = bronze_snapshot_ids(
            bronze_conn,
            underlying=args.underlying,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(f"Discovered {len(snapshots)} Bronze snapshots")

        built = skipped = failed = 0
        for source_label, snapshot_id, capture_event_id, envelope_hash, recording_fingerprint in snapshots:
            if args.mode == "dry-run":
                print(f"DRY-RUN snapshot_id={snapshot_id} source_label={source_label}")
                continue
            try:
                result = build_silver_snapshot(
                    bronze_conn,
                    silver_conn,
                    source_label=source_label,
                    snapshot_id=snapshot_id,
                    capture_event_id=capture_event_id,
                    envelope_hash=envelope_hash,
                    recording_fingerprint=recording_fingerprint,
                    actor_id=args.actor_id,
                    code_revision=args.code_revision,
                )
                if result["status"] == "SKIPPED":
                    skipped += 1
                    print(f"SKIPPED {snapshot_id}")
                else:
                    built += 1
                    print(
                        f"BUILT {snapshot_id} observations={result['observation_count']} "
                        f"quarantined={result['quarantined_count']}"
                    )
            except Exception as exc:
                failed += 1
                print(f"FAILED {snapshot_id} {type(exc).__name__}: {exc}")

        print(f"Complete: built={built} skipped={skipped} failed={failed} mode={args.mode}")
        return 0 if failed == 0 else 2
    finally:
        bronze_conn.close()
        silver_conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
