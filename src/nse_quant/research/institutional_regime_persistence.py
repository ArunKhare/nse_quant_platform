"""Institutional regime evidence persistence.

Persists the full regime payload (as_of, input timestamps, availability flags,
classifier_version, regime_label, components) with first-write semantics.
Observational only; never grants decision eligibility or enables live trading.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

TABLE = "institutional_regime_evidence"
VERSION = "institutional-regime-evidence@1"


class PersistenceRejected(ValueError):
    """Fixed diagnostic codes; operational failures propagate."""


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _clock(value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise PersistenceRejected("AWARE_CLOCK_REQUIRED")
    return value.astimezone(UTC)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return _clock(value).isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def initialize(target: Any) -> None:
    target.execute(
        f"CREATE TABLE IF NOT EXISTS {TABLE} ("
        "evidence_id VARCHAR PRIMARY KEY,"
        "as_of TIMESTAMPTZ NOT NULL,"
        "symbol VARCHAR NOT NULL,"
        "classifier_version VARCHAR NOT NULL,"
        "regime_label VARCHAR,"
        "complete BOOLEAN NOT NULL,"
        "payload_json VARCHAR NOT NULL,"
        "recorded_at TIMESTAMPTZ NOT NULL)"
    )


def evidence_id(
    *,
    as_of: datetime,
    symbol: str,
    classifier_version: str,
) -> str:
    import hashlib

    canonical = json.dumps(
        {
            "version": VERSION,
            "as_of": _clock(as_of).isoformat(),
            "symbol": symbol,
            "classifier_version": classifier_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def persist_regime_evidence(
    target: Any,
    *,
    payload: dict[str, Any],
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    if type(payload) is not dict:
        raise PersistenceRejected("REGIME_PAYLOAD_OBJECT_REQUIRED")
    required = {"as_of", "symbol", "classifier_version", "regime_label", "complete", "components"}
    if not required.issubset(payload):
        raise PersistenceRejected("REGIME_PAYLOAD_FIELDS_REQUIRED")
    if type(actor_id) is not str or not 1 <= len(actor_id) <= 128 or actor_id != actor_id.strip():
        raise PersistenceRejected("BOUNDED_ACTOR_REQUIRED")
    if type(code_revision) is not str or len(code_revision) != 40:
        raise PersistenceRejected("CODE_REVISION_REQUIRED")

    as_of = _clock(payload["as_of"])
    symbol = payload["symbol"]
    classifier_version = payload["classifier_version"]
    if type(symbol) is not str or not symbol:
        raise PersistenceRejected("SYMBOL_REQUIRED")
    if type(classifier_version) is not str or not classifier_version:
        raise PersistenceRejected("CLASSIFIER_VERSION_REQUIRED")

    evidence_id_value = evidence_id(
        as_of=as_of,
        symbol=symbol,
        classifier_version=classifier_version,
    )
    if target.execute(
        f"SELECT 1 FROM {TABLE} WHERE evidence_id=? LIMIT 1", [evidence_id_value]
    ).fetchone():
        raise PersistenceRejected("REGIME_EVIDENCE_FIRST_WRITE_ONLY")

    payload_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=_json_default,
    )
    recorded_at = _clock(datetime.now(UTC))
    target.execute(
        f"INSERT INTO {TABLE} VALUES (?,?,?,?,?,?,?,?)",
        [
            evidence_id_value,
            as_of,
            symbol,
            classifier_version,
            payload.get("regime_label"),
            bool(payload.get("complete", False)),
            payload_json,
            recorded_at,
        ],
    )
    return dict(
        evidence_id=evidence_id_value,
        as_of=as_of.isoformat(),
        symbol=symbol,
        classifier_version=classifier_version,
        regime_label=payload.get("regime_label"),
        complete=bool(payload.get("complete", False)),
        recorded_at=recorded_at.isoformat(),
        decision_eligibility_asserted=False,
    )


def read_regime_evidence(
    target: Any,
    *,
    evidence_id: str,
) -> dict[str, Any]:
    if not _pin(evidence_id):
        raise PersistenceRejected("EXACT_REGIME_EVIDENCE_PIN_REQUIRED")
    row = target.execute(
        f"SELECT as_of,symbol,classifier_version,regime_label,complete,payload_json,recorded_at "
        f"FROM {TABLE} WHERE evidence_id=? LIMIT 1",
        [evidence_id],
    ).fetchone()
    if row is None:
        raise PersistenceRejected("REGIME_EVIDENCE_NOT_FOUND")
    payload = json.loads(row[5])
    return dict(
        evidence_id=evidence_id,
        as_of=row[0].isoformat(),
        symbol=row[1],
        classifier_version=row[2],
        regime_label=row[3],
        complete=row[4],
        payload=payload,
        recorded_at=row[6].isoformat(),
        decision_eligibility_asserted=False,
    )
