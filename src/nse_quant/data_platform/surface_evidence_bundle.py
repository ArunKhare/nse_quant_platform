"""Offline, content-pinned S2 surface evidence; no publication or decision authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any

from nse_quant.analytics import constant_maturity_inputs as cm

VERSION = "s2-surface-evidence@1"
MAX_BYTES = 8 * 1024 * 1024
MAX_QUOTES = 4096


def _encode(value: Any) -> bytes:
    def clock(item: Any) -> str:
        if not isinstance(item, datetime) or item.utcoffset() is None:
            raise ValueError("AWARE_CLOCK_REQUIRED")
        return item.astimezone(UTC).isoformat()

    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=clock).encode()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _time(value: str) -> datetime:
    at = datetime.fromisoformat(value)
    if at.utcoffset() is None:
        raise ValueError("AWARE_CLOCK_REQUIRED")
    return at.astimezone(UTC)


def _shape(value: Any, keys: str) -> None:
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise ValueError("UNEXPECTED_EVIDENCE_FIELDS")


def _point(cls: Any, row: dict[str, Any]) -> Any:
    return cls(**{k: _time(v) if k in {"expiry_close", "source_time", "received_at"} else v for k, v in row.items()})


def _evaluate(doc: dict[str, Any]) -> dict[str, Any]:
    _shape(doc, "policy premiums calendar forwards")
    policy = doc["policy"]
    _shape(policy, "as_of max_age_seconds max_source_gap_seconds kernel delta")
    if (policy["kernel"], policy["delta"]) != (cm.VERSION, cm.DELTA_CONVENTION):
        raise ValueError("UNSUPPORTED_SURFACE_PROFILE")
    at = _time(policy["as_of"])
    calendar = doc["calendar"]
    _shape(calendar, "source available_at closes")
    if not calendar["source"] or _time(calendar["available_at"]) > at:
        raise ValueError("CALENDAR_NOT_AVAILABLE")
    closes = {_time(value) for value in calendar["closes"]}
    if len(closes) != len(calendar["closes"]):
        raise ValueError("DUPLICATE_CALENDAR_CLOSE")
    premiums = doc["premiums"]
    if not isinstance(premiums, list) or not 1 <= len(premiums) <= MAX_QUOTES:
        raise ValueError("PREMIUM_COUNT_BOUND")
    quotes = [_point(cm.PremiumPoint, row) for row in premiums]
    if not {q.expiry_close for q in quotes} <= closes:
        raise ValueError("CALENDAR_CLOSE_NOT_LINKED")
    tokens = {q.token: q for q in quotes}
    if len(tokens) != len(quotes):
        raise ValueError("DUPLICATE_PREMIUM_TOKEN")
    limits = {k: policy[k] for k in ("max_age_seconds", "max_source_gap_seconds")}
    forwards = []
    seen = set()
    for row in doc["forwards"]:
        _shape(row, "expiry_close rate kind evidence")
        close = _time(row["expiry_close"])
        if close in seen or close not in closes:
            raise ValueError("FORWARD_CLOSE_NOT_UNIQUE_OR_LINKED")
        seen.add(close)
        rate = row["rate"]
        _shape(rate, "annual_rate convention source available_at")
        if rate["convention"] != "annual_continuously_compounded" or not rate["source"]:
            raise ValueError("UNSUPPORTED_RATE_EVIDENCE")
        if _time(rate["available_at"]) > at:
            raise ValueError("RATE_NOT_AVAILABLE")
        evidence = row["evidence"]
        ref = sha256(_encode(row))
        if row["kind"] == "matched_forward_observation":
            _shape(evidence, "underlying forward source source_time received_at")
            if evidence["underlying"] != quotes[0].underlying or not evidence["source"]:
                raise ValueError("FORWARD_IDENTITY_MISMATCH")
            forwards.append(
                _point(
                    cm.ForwardPoint,
                    dict(evidence, expiry_close=row["expiry_close"], rate=rate["annual_rate"], reference_id=ref),
                )
            )
        elif row["kind"] == "synthetic_parity":
            _shape(evidence, "call_token put_token")
            call, put = (tokens.get(evidence[key]) for key in ("call_token", "put_token"))
            if call is None or put is None or call.expiry_close != close or put.expiry_close != close:
                raise ValueError("PARITY_PAIR_NOT_LINKED")
            forward = cm.synthetic_forward_from_pair(call, put, as_of=at, rate=rate["annual_rate"], **limits)
            forwards.append(replace(forward, reference_id=ref))
        else:
            raise ValueError("UNSUPPORTED_FORWARD_KIND")
    result = asdict(cm.build_surface_inputs(quotes, forwards, as_of=at, **limits))
    result["calendar_reference_id"] = sha256(_encode(calendar))
    return result


def build_bundle(evidence: dict[str, Any]) -> bytes:
    """Create canonical bytes from reviewed structured inputs; no external fetches."""
    inputs = _encode(evidence)
    if not 0 < len(inputs) <= MAX_BYTES:
        raise ValueError("INPUT_BYTE_BOUND")
    doc = json.loads(inputs)
    raw = _encode(dict(version=VERSION, evidence=doc, result=_evaluate(doc)))
    if len(raw) > MAX_BYTES:
        raise ValueError("BUNDLE_BYTE_BOUND")
    return raw


def replay_bundle(raw: bytes, *, expected_sha256: str) -> dict[str, Any]:
    """Require an external pin, then recompute and compare the complete bundle."""
    if not 0 < len(raw) <= MAX_BYTES or sha256(raw) != expected_sha256:
        raise ValueError("BUNDLE_PIN_OR_BOUND_MISMATCH")
    doc = json.loads(raw)
    _shape(doc, "version evidence result")
    if doc["version"] != VERSION or build_bundle(doc["evidence"]) != raw:
        raise ValueError("SURFACE_REPLAY_MISMATCH")
    return doc["result"]
