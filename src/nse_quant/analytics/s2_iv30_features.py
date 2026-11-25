"""Deterministic observational IV30 features; no regime, VRP or entry authority."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from nse_quant.core.iv_statistics import iv_percentile_and_rank

VERSION = "s2-observational-iv30-features@1"
LIVE_VERSION = "kite_india_vix_observation_v1"
IST = ZoneInfo("Asia/Kolkata")
MAX_BYTES = 6 * 1024 * 1024
MAX_SAMPLES = 4096


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _time(value: str) -> datetime:
    at = datetime.fromisoformat(value)
    if at.utcoffset() is None:
        raise ValueError("S2_AWARE_FEATURE_CLOCK_REQUIRED")
    return at.astimezone(UTC)


def _positive(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("S2_POSITIVE_FINITE_IV_REQUIRED")
    return float(value)


def _provenance(value: dict[str, Any], cutoff: datetime) -> dict[str, Any]:
    keys = {"observation_id", "materialization_sha256", "revision_id", "materialization_available_at"}
    if type(value) is not dict or set(value) != keys:
        raise ValueError("S2_EXACT_FEATURE_PROVENANCE_REQUIRED")
    if any(not _pin(value[key]) for key in keys - {"materialization_available_at"}):
        raise ValueError("S2_EXACT_FEATURE_PINS_REQUIRED")
    if _time(value["materialization_available_at"]) > cutoff:
        raise ValueError("S2_MATERIALIZATION_NOT_YET_AVAILABLE")
    return dict(value)


def _finish(payload: dict[str, Any]) -> bytes:
    result = canonical(
        dict(
            version=VERSION,
            **payload,
            iv30_source="india_vix",
            mode="observation",
            regime_label=None,
            publication_asserted=False,
            decision_eligibility_asserted=False,
            historical_availability_asserted=False,
            acquisition_authenticity_verified=False,
            atomic_cross_database_snapshot_asserted=False,
        )
    )
    if len(result) > MAX_BYTES:
        raise ValueError("S2_FEATURE_BYTE_BOUND")
    return result


def build_eod_feature(
    history: bytes,
    *,
    expected_history_sha256: str,
    provenance: dict[str, Any],
    as_of: str,
    trade_date: str,
    lookback: int = 252,
    minimum_history: int = 120,
    max_age_calendar_days: int = 4,
) -> bytes:
    """EOD research metric, never a substitute for fresh intraday IV30.

    IVP compares selected close with prior available daily rows (strict less).
    IVR uses at most lookback closes INCLUDING selected close; both denominators
    and date ranges are retained. Session completeness is not inferred from rows.
    """
    from nse_quant.analytics import s2_iv30_history as eod

    at = _time(as_of)
    pins = _provenance(provenance, at)
    if type(lookback) is not int or type(minimum_history) is not int or not 120 <= minimum_history <= lookback <= 252:
        raise ValueError("S2_DAILY_HISTORY_POLICY_REQUIRED")
    if type(max_age_calendar_days) is not int or not 1 <= max_age_calendar_days <= 31:
        raise ValueError("S2_BOUNDED_EOD_FRESHNESS_REQUIRED")
    selected_day = date.fromisoformat(trade_date)
    age = (at.astimezone(IST).date() - selected_day).days
    if not 1 <= age <= max_age_calendar_days:
        raise ValueError("S2_STALE_OR_NOT_COMPLETED_EOD")
    doc = eod.replay_history(history, expected_sha256=expected_history_sha256)
    if _time(doc["request"]["as_of"]) > at:
        raise ValueError("S2_FUTURE_HISTORY_POLICY")
    if doc["iv30_source"] != "india_vix":
        raise ValueError("S2_IV_SOURCE_MIXING_FORBIDDEN")
    available = [row for row in doc["rows"] if _time(row["available_at"]) <= at]
    selected = [row for row in available if row["trade_date"] == trade_date]
    if len(selected) != 1:
        raise ValueError("S2_EXACT_AVAILABLE_EOD_REQUIRED")
    value = _positive(selected[0]["iv30"])
    prior = [row for row in available if row["trade_date"] < trade_date][-lookback:]
    ivp, ivr, ivr_observation_count = iv_percentile_and_rank(
        [row["iv30"] for row in prior],
        value,
        lookback=lookback,
        minimum_history=minimum_history,
    )
    rank_rows = [*prior[-(lookback - 1) :], selected[0]] if lookback > 1 else [selected[0]]
    enough = ivp is not None
    reasons = []
    if not enough:
        reasons.append("INSUFFICIENT_PRIOR_DAILY_HISTORY")
    elif high == low:
        reasons.append("DEGENERATE_IVR_RANGE")
    return _finish(
        dict(
            feature_kind="eod_iv30_statistics",
            as_of=at.isoformat(),
            trade_date=trade_date,
            source_time=None,
            iv30=value,
            sampling="supplied_eod_file_close",
            age_calendar_days=age,
            max_age_calendar_days=max_age_calendar_days,
            lookback=lookback,
            minimum_history=minimum_history,
            prior_observation_count=len(prior),
            prior_range=[prior[0]["trade_date"], prior[-1]["trade_date"]] if prior else None,
            iv_percentile=ivp,
            iv_rank=ivr,
            ivr_observation_count=ivr_observation_count,
            ivr_range=[rank_rows[0]["trade_date"], rank_rows[-1]["trade_date"]],
            rank_definition="prior-strict-less-IVP;inclusive-current-rolling-IVR@1",
            quality_state="valid_observation" if enough else "insufficient_history",
            reason_codes=reasons,
            session_coverage_verified=False,
            live_vrp_input_asserted=False,
            provenance=pins,
            history_sha256=expected_history_sha256,
        )
    )


def build_live_feature(
    samples: dict[str, dict[str, Any]], *, provenance: dict[str, Any], as_of: str, max_age_seconds: float = 300
) -> bytes:
    """Caller must native-replay every sample; this arithmetic kernel is not proof.

    Reject future dependent samples rather than silently filtering a future-built
    artifact into an earlier historical feature. Never use minute bucket time as
    the actual latest quote timestamp.
    """
    at = _time(as_of)
    pins = _provenance(provenance, at)
    age_limit = _positive(max_age_seconds)
    if type(samples) is not dict or not 1 <= len(samples) <= MAX_SAMPLES or any(not _pin(pin) for pin in samples):
        raise ValueError("S2_EXACT_LIVE_SAMPLE_SET_REQUIRED")
    selected = []
    tokens = set()
    times = set()
    for revision, record in samples.items():
        if (
            type(record) is not dict
            or record.get("quality_state") != "valid_observation"
            or record.get("decision_eligibility_asserted") is not False
        ):
            raise ValueError("S2_VALID_NATIVE_VIX_OBSERVATION_REQUIRED")
        value = record.get("observation")
        if (
            type(value) is not dict
            or value.get("version") != LIVE_VERSION
            or value.get("iv30_source") != "india_vix"
            or value.get("mode") != "observation"
            or value.get("decision_eligibility_asserted") is not False
            or value.get("quote_key") != "NSE:INDIA VIX"
        ):
            raise ValueError("S2_LIVE_VIX_PROFILE_MISMATCH")
        for key in ("raw_payload_sha256", "instrument_reference_sha256"):
            if not _pin(value.get(key)):
                raise ValueError("S2_LIVE_VIX_REFERENCE_PIN_REQUIRED")
        token = value.get("instrument_token")
        if type(token) is not int or token <= 0:
            raise ValueError("S2_LIVE_VIX_TOKEN_REQUIRED")
        tokens.add(token)
        stamp, received, observed = (_time(value[key]) for key in ("source_time", "received_at", "as_of"))
        if not stamp <= received <= observed <= at:
            raise ValueError("S2_FUTURE_OR_UNORDERED_LIVE_DEPENDENCY")
        if stamp in times:
            raise ValueError("S2_AMBIGUOUS_LIVE_SOURCE_TIME")
        times.add(stamp)
        iv30, percent = _positive(value.get("iv30")), _positive(value.get("value_percent"))
        if not math.isclose(iv30 * 100, percent, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("S2_LIVE_VIX_UNITS_MISMATCH")
        selected.append((stamp, revision, value))
    if len(tokens) != 1:
        raise ValueError("S2_LIVE_VIX_IDENTITY_CHANGED")
    stamp, revision, value = max(selected, key=lambda item: item[0])
    age = (at - stamp).total_seconds()
    if age > age_limit:
        raise ValueError("S2_STALE_LIVE_IV30")
    return _finish(
        dict(
            feature_kind="live_iv30_observation",
            as_of=at.isoformat(),
            iv30=value["iv30"],
            source_time=stamp.isoformat(),
            received_at=value["received_at"],
            age_seconds=age,
            max_age_seconds=age_limit,
            selected_revision_id=revision,
            source_revisions=sorted(samples),
            instrument_token=value["instrument_token"],
            raw_payload_sha256=value["raw_payload_sha256"],
            instrument_reference_sha256=value["instrument_reference_sha256"],
            within_regular_time_window=value["within_regular_time_window"],
            session_calendar_verified=value["session_calendar_verified"],
            session_is_open=value["session_is_open"],
            quality_state="valid_observation",
            provenance=pins,
            model_suitability_verified=False,
            vrp_gate_passed=False,
        )
    )
