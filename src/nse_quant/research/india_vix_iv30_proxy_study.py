"""Audited NIFTY India-VIX/internal-CM paired proxy study; offline and non-authoritative."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from nse_quant.data_platform import india_vix_recording as vix
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform import native_surface_recording as surface
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.research.india_vix_iv30_suitability import (
    ProxyPair,
    evaluate_india_vix_iv30_proxy,
)

VERSION = "india-vix-iv30-proxy-study@1"
POLICY_COMMAND = "research.preregister_vix_proxy_policy@1"
PAIRSET_COMMAND = "research.persist_vix_proxy_pairset@1"
REPORT_COMMAND = "research.evaluate_vix_proxy_pairset@1"
POLICIES = "silver.vix_proxy_policies"
PAIRSETS = "silver.vix_proxy_pairsets"
REPORTS = "silver.vix_proxy_reports"
SCHEMA_VERSIONS = "silver.vix_proxy_study_schema_versions"
IST = ZoneInfo("Asia/Kolkata")
CONDITIONS = ("ELEVATED_VOLATILITY", "EVENT", "EXPIRY", "NORMAL", "QUIET", "STRUCTURAL")
MAX_PAIRSET_BYTES = 64 * 1024 * 1024
MAX_PAIRS = 10000


def _utc(value: datetime | str) -> datetime:
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.utcoffset() is None:
        raise ValueError("AWARE_STUDY_CLOCK_REQUIRED")
    return result.astimezone(UTC)


def _pin(value: object) -> bool:
    return base.pin(value)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=lambda item: item.isoformat() if isinstance(item, (datetime, date)) else None,
    ).encode()


@dataclass(frozen=True)
class ProxyAcceptancePolicy:
    """Explicitly preregistered holdout tolerances; no defaults are inferred."""

    max_abs_bias: float
    max_mae: float
    max_rmse: float
    max_p90_absolute_error: float
    min_correlation: float
    min_ols_slope: float
    max_ols_slope: float
    minimum_holdout_pairs_per_condition: int = 20
    required_conditions: tuple[str, ...] = CONDITIONS
    holdout_fraction: float = 0.30
    max_pair_gap_seconds: float = 30.0
    max_source_age_seconds: float = 300.0

    def validate(self) -> None:
        for name in (
            "max_abs_bias",
            "max_mae",
            "max_rmse",
            "max_p90_absolute_error",
            "max_pair_gap_seconds",
            "max_source_age_seconds",
            "min_ols_slope",
            "max_ols_slope",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError("POSITIVE_FINITE_POLICY_LIMIT_REQUIRED")
        if (
            isinstance(self.min_correlation, bool)
            or not isinstance(self.min_correlation, (int, float))
            or not math.isfinite(self.min_correlation)
            or not -1 <= self.min_correlation <= 1
            or isinstance(self.holdout_fraction, bool)
            or not isinstance(self.holdout_fraction, (int, float))
            or not math.isfinite(self.holdout_fraction)
            or isinstance(self.max_pair_gap_seconds, bool)
            or not isinstance(self.max_pair_gap_seconds, (int, float))
            or not math.isfinite(self.max_pair_gap_seconds)
            or isinstance(self.max_source_age_seconds, bool)
            or not isinstance(self.max_source_age_seconds, (int, float))
            or not math.isfinite(self.max_source_age_seconds)
            or self.min_ols_slope >= self.max_ols_slope
            or type(self.minimum_holdout_pairs_per_condition) is not int
            or self.minimum_holdout_pairs_per_condition < 2
            or type(self.required_conditions) is not tuple
            or self.required_conditions != CONDITIONS
            or not 0.1 <= self.holdout_fraction <= 0.5
        ):
            raise ValueError("INVALID_PROXY_ACCEPTANCE_POLICY")


@dataclass(frozen=True)
class ProxyPairRequest:
    """Exact retained source pins plus a separately reviewed condition artifact."""

    vix_silver_revision_id: str
    surface_observation_id: str
    surface_sha256: str
    condition_artifact: bytes
    condition_sha256: str


def _condition_artifact(raw: bytes, expected_sha256: str, pair_as_of: datetime) -> tuple[tuple[str, ...], str]:
    if (
        type(raw) is not bytes
        or not 0 < len(raw) <= 65536
        or not base.pin(expected_sha256)
        or base.sha(raw) != expected_sha256
    ):
        raise ValueError("CONDITION_ARTIFACT_PIN_OR_BOUND_MISMATCH")
    doc = json.loads(raw)
    if (
        not isinstance(doc, dict)
        or set(doc) != {"source", "trade_date", "as_of", "available_at", "tags"}
        or _canonical(doc) != raw
        or not isinstance(doc["source"], str)
        or not doc["source"].strip()
        or not isinstance(doc["tags"], list)
        or any(type(tag) is not str for tag in doc["tags"])
        or not doc["tags"]
        or doc["tags"] != sorted(set(doc["tags"]))
        or not set(doc["tags"]) <= set(CONDITIONS)
    ):
        raise ValueError("REVIEWED_CONDITION_ARTIFACT_REQUIRED")
    trade_date = date.fromisoformat(doc["trade_date"])
    as_of, available_at = _utc(doc["as_of"]), _utc(doc["available_at"])
    if (
        trade_date != pair_as_of.astimezone(IST).date()
        or as_of.astimezone(IST).date() != trade_date
        or as_of > pair_as_of
        or available_at > pair_as_of
    ):
        raise ValueError("CONDITION_EVIDENCE_NOT_AVAILABLE_FOR_PAIR")
    return tuple(doc["tags"]), expected_sha256


def _vix_available_at(silver: Any, revision_id: str) -> tuple[datetime, dict[str, Any]]:
    sets = vix.table(silver, vix.SETS)
    context_raw, context_hash, recorded_at = vix.one(
        silver,
        f"SELECT context,context_sha256,recorded_at FROM {sets} WHERE revision_id=?",
        [revision_id],
    )
    context = bytes(context_raw)
    if base.sha(context) != context_hash:
        raise ValueError("VIX_CONTEXT_HASH_MISMATCH")
    doc = json.loads(context)
    if (
        doc.get("version") != vix.VERSION
        or doc.get("iv30_source") != "india_vix"
        or base.sha(base.canonical([vix.VERSION, context_hash])) != revision_id
    ):
        raise ValueError("VIX_REVISION_IDENTITY_MISMATCH")
    jobs = vix.table(silver, "medallion_audit.jobs")
    events = vix.table(silver, "medallion_audit.job_events")
    rows = silver.execute(
        f"SELECT j.job_id,j.created_at,e.recorded_at FROM {jobs} j "
        f"JOIN {events} e ON e.job_id=j.job_id "
        "WHERE j.command_name=? AND j.scope_ref=? AND j.config_hash=? "
        "AND e.event_index=3 AND e.state='SUCCEEDED' LIMIT 2",
        [vix.NORMALIZE, vix.SOURCE, context_hash],
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("VIX_ORIGINAL_SUCCESSFUL_AUDIT_REQUIRED")
    available_at = max(_utc(recorded_at), _utc(rows[0][2]))
    return available_at, doc


def _surface_available_at(silver: Any, observation_id: str, expected_sha256: str) -> tuple[datetime, dict[str, Any]]:
    doc, job_id = surface.read_recording_metadata(
        silver, observation_id=observation_id, expected_sha256=expected_sha256
    )
    jobs = vix.table(silver, "medallion_audit.jobs")
    events = vix.table(silver, "medallion_audit.job_events")
    audit_rows = silver.execute(
        f"SELECT j.created_at,e.recorded_at FROM {jobs} j "
        f"JOIN {events} e ON e.job_id=j.job_id "
        "WHERE j.job_id=? AND e.event_index=3 AND e.state='SUCCEEDED' LIMIT 2",
        [job_id],
    ).fetchall()
    if len(audit_rows) != 1 or doc.get("version") != surface.VERSION:
        raise ValueError("SURFACE_ORIGINAL_SUCCESSFUL_AUDIT_REQUIRED")
    return _utc(audit_rows[0][1]), doc


def replay_matched_pair(
    vix_bronze: Any,
    vix_silver: Any,
    option_bronze: Any,
    surface_silver: Any,
    request: ProxyPairRequest,
    *,
    max_pair_gap_seconds: float = 30.0,
    max_source_age_seconds: float = 300.0,
) -> ProxyPair:
    """Replay both exact sources and form a pair at the latest source-availability time."""
    for name, value in (
        ("MAX_PAIR_GAP", max_pair_gap_seconds),
        ("MAX_SOURCE_AGE", max_source_age_seconds),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name}_MUST_BE_POSITIVE_FINITE")
    connections = (vix_bronze, vix_silver, option_bronze, surface_silver)
    for connection in connections:
        base.readonly(connection)
    for index, connection in enumerate(connections):
        for other in connections[index + 1 :]:
            base.separate(connection, other)
    if not _pin(request.vix_silver_revision_id) or not _pin(request.surface_observation_id) or not _pin(
        request.surface_sha256
    ):
        raise ValueError("EXACT_PROXY_SOURCE_PINS_REQUIRED")
    vix_record = vix.replay_vix_silver(vix_bronze, vix_silver, revision_id=request.vix_silver_revision_id)
    if (
        vix_record.get("quality_state") != "valid_observation"
        or vix_record.get("observation") is None
        or vix_record.get("decision_eligibility_asserted") is not False
    ):
        raise ValueError("VALID_OBSERVATIONAL_VIX_REQUIRED")
    vix_observation = vix_record["observation"]
    if (
        vix_observation.get("iv30_source") != "india_vix"
        or vix_observation.get("mode") != "observation"
        or vix_observation.get("decision_eligibility_asserted") is not False
    ):
        raise ValueError("INDIA_VIX_OBSERVATION_IDENTITY_REQUIRED")
    surface_result = surface.replay(
        option_bronze,
        surface_silver,
        observation_id=request.surface_observation_id,
        expected_sha256=request.surface_sha256,
    )
    if (
        surface_result.get("underlying") != "NIFTY"
        or surface_result.get("iv_source") != "internal_cm"
        or surface_result.get("mode") != "observation"
        or surface_result.get("version") != "constant_maturity_black76_inputs_v1"
        or surface_result.get("decision_eligibility_asserted") is not False
    ):
        raise ValueError("NIFTY_INTERNAL_CM_OBSERVATION_REQUIRED")
    vix_available, vix_context = _vix_available_at(vix_silver, request.vix_silver_revision_id)
    surface_available, surface_doc = _surface_available_at(
        surface_silver, request.surface_observation_id, request.surface_sha256
    )
    vix_policy = vix_context["policy"]
    surface_policy = surface_doc["policy"]
    allowed_age = min(
        float(max_source_age_seconds),
        float(vix_policy["max_age_seconds"]),
        float(surface_policy["max_age_seconds"]),
    )
    source_times = (_utc(vix_observation["source_time"]), _utc(surface_result["source_time"]))
    received_times = (_utc(vix_observation["received_at"]), _utc(surface_result["received_at"]))
    observation_as_of = (_utc(vix_observation["as_of"]), _utc(surface_result["as_of"]))
    if (
        vix_available < max(received_times[0], observation_as_of[0])
        or surface_available < max(received_times[1], observation_as_of[1])
    ):
        raise ValueError("SOURCE_AUDIT_PRECEDES_OBSERVATION_AVAILABILITY")
    pair_as_of = max(vix_available, surface_available, *received_times)
    if any(value > pair_as_of for value in (*source_times, *received_times)):
        raise ValueError("PAIR_SOURCE_CLOCK_AFTER_AS_OF")
    if max((pair_as_of - value).total_seconds() for value in source_times) > allowed_age:
        raise ValueError("PAIR_SOURCE_NOT_AVAILABLE_WITHIN_FRESHNESS_WINDOW")
    if abs((source_times[0] - source_times[1]).total_seconds()) > max_pair_gap_seconds:
        raise ValueError("SYNCHRONIZED_SOURCE_PAIR_REQUIRED")
    if _utc(vix_observation["as_of"]) > pair_as_of or _utc(surface_result["as_of"]) > pair_as_of:
        raise ValueError("PAIR_OBSERVATION_AS_OF_AFTER_AVAILABILITY")
    tags, condition_pin = _condition_artifact(request.condition_artifact, request.condition_sha256, pair_as_of)
    return ProxyPair(
        trade_date=pair_as_of.astimezone(IST).date(),
        as_of=pair_as_of,
        india_vix_iv30=float(vix_observation["iv30"]),
        india_vix_source_time=source_times[0],
        india_vix_received_at=received_times[0],
        india_vix_revision_sha256=request.vix_silver_revision_id,
        surface_iv30=float(surface_result["iv30"]["iv"]),
        surface_source_time=source_times[1],
        surface_received_at=received_times[1],
        surface_batch_sha256=request.surface_sha256,
        surface_version=surface_result["version"],
        surface_iv_source=surface_result["iv_source"],
        surface_mode=surface_result["mode"],
        surface_decision_eligibility_asserted=False,
        underlying="NIFTY",
        vix_silver_revision_id=request.vix_silver_revision_id,
        surface_observation_id=request.surface_observation_id,
        vix_available_at=vix_available,
        surface_available_at=surface_available,
        condition_tags=tags,
        condition_evidence_sha256=condition_pin,
        condition_evidence_json=request.condition_artifact.decode("utf-8"),
    )


def _policy_bytes(policy: ProxyAcceptancePolicy) -> bytes:
    policy.validate()
    return _canonical(asdict(policy))


def _table(conn: Any, name: str) -> str:
    return vix.table(conn, name)


def _file_backed(conn: Any) -> None:
    paths = [row[2] for row in conn.execute("PRAGMA database_list").fetchall() if row[2]]
    if not paths or any(not Path(value).is_file() for value in paths):
        raise ValueError("FILE_BACKED_STUDY_DATABASE_REQUIRED")


def initialize_study_store(conn: Any, *, actor_id: str, code_revision: str) -> None:
    vix.execution(actor_id, code_revision)
    _file_backed(conn)
    vix.silver_target(conn)
    AuditLedger(conn).initialize()
    conn.execute("CREATE SCHEMA IF NOT EXISTS silver")
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {_table(conn, SCHEMA_VERSIONS)} "
        "(version INTEGER PRIMARY KEY,applied_at TIMESTAMPTZ NOT NULL)"
    )
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {_table(conn, POLICIES)} "
        "(policy_id VARCHAR PRIMARY KEY,body BLOB NOT NULL,registered_at TIMESTAMPTZ NOT NULL,job_id VARCHAR NOT NULL)"
    )
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {_table(conn, PAIRSETS)} "
        "(pair_set_id VARCHAR PRIMARY KEY,policy_id VARCHAR NOT NULL,body BLOB NOT NULL,"
        "recorded_at TIMESTAMPTZ NOT NULL,job_id VARCHAR NOT NULL)"
    )
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {_table(conn, REPORTS)} "
        "(pair_set_id VARCHAR NOT NULL,report_sha256 VARCHAR NOT NULL,body BLOB NOT NULL,"
        "job_id VARCHAR NOT NULL,PRIMARY KEY(pair_set_id,report_sha256))"
    )
    versions = conn.execute(
        f"SELECT version FROM {_table(conn, SCHEMA_VERSIONS)} ORDER BY version"
    ).fetchall()
    if versions not in ([], [(1,)]):
        raise ValueError("UNSUPPORTED_PROXY_STUDY_SCHEMA_VERSION")
    if not versions:
        conn.execute(
            f"INSERT INTO {_table(conn, SCHEMA_VERSIONS)} VALUES (1, ?)", [datetime.now(UTC)]
        )
    expected_columns = {
        POLICIES: ("policy_id", "body", "registered_at", "job_id"),
        PAIRSETS: ("pair_set_id", "policy_id", "body", "recorded_at", "job_id"),
        REPORTS: ("pair_set_id", "report_sha256", "body", "job_id"),
    }
    for table_name, expected in expected_columns.items():
        actual = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_catalog=current_database() AND table_schema='silver' AND table_name=? "
            "ORDER BY ordinal_position",
            [table_name.split(".", maxsplit=1)[1]],
        ).fetchall()
        if tuple(row[0] for row in actual) != expected:
            raise ValueError("PROXY_STUDY_TABLE_SCHEMA_MISMATCH")


def register_acceptance_policy(
    conn: Any,
    policy: ProxyAcceptancePolicy,
    *,
    actor_id: str,
    code_revision: str,
) -> str:
    vix.execution(actor_id, code_revision)
    _file_backed(conn)
    vix.silver_target(conn)
    raw = _policy_bytes(policy)
    policy_id = base.sha(raw)
    table = _table(conn, POLICIES)
    existing = conn.execute(
        f"SELECT body,job_id FROM {table} WHERE policy_id=? LIMIT 2", [policy_id]
    ).fetchall()
    if existing:
        if len(existing) != 1 or bytes(existing[0][0]) != raw:
            raise ValueError("POLICY_REGISTRATION_CONFLICT")
        vix.audit(conn, existing[0][1], POLICY_COMMAND, policy_id, policy_id)
        return policy_id
    ledger = AuditLedger(conn)
    job = ledger.plan_job(
        command_name=POLICY_COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref=policy_id,
        config_hash=policy_id,
    )
    with ledger.execution(job):
        conn.execute(f"INSERT INTO {table} VALUES (?,?,?,?)", [policy_id, raw, datetime.now(UTC), job])
    return policy_id


def _load_policy(conn: Any, policy_id: str) -> tuple[ProxyAcceptancePolicy, datetime]:
    if not _pin(policy_id):
        raise ValueError("EXACT_PREREGISTERED_POLICY_PIN_REQUIRED")
    rows = conn.execute(
        f"SELECT body,registered_at,job_id FROM {_table(conn, POLICIES)} WHERE policy_id=? LIMIT 2",
        [policy_id],
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("PREREGISTERED_POLICY_NOT_FOUND")
    raw, registered_at, job = bytes(rows[0][0]), _utc(rows[0][1]), rows[0][2]
    if base.sha(raw) != policy_id:
        raise ValueError("POLICY_REGISTRATION_HASH_MISMATCH")
    vix.audit(conn, job, POLICY_COMMAND, policy_id, policy_id)
    doc = json.loads(raw)
    doc["required_conditions"] = tuple(doc["required_conditions"])
    policy = ProxyAcceptancePolicy(**doc)
    policy.validate()
    return policy, registered_at


def persist_pair_set(
    vix_bronze: Any,
    vix_silver: Any,
    option_bronze: Any,
    surface_silver: Any,
    target: Any,
    *,
    requests: Sequence[ProxyPairRequest],
    policy_id: str,
    actor_id: str,
    code_revision: str,
) -> str:
    """Replay all requested source pairs, then persist one immutable preregistered study set."""
    vix.execution(actor_id, code_revision)
    _file_backed(target)
    vix.silver_target(target)
    if not isinstance(requests, Sequence) or isinstance(requests, (str, bytes)) or not 1 <= len(requests) <= MAX_PAIRS:
        raise ValueError("BOUNDED_PROXY_PAIR_REQUESTS_REQUIRED")
    for source in (vix_bronze, vix_silver, option_bronze, surface_silver):
        _file_backed(source)
        base.readonly(source)
        base.separate(source, target)
    for index, source in enumerate((vix_bronze, vix_silver, option_bronze, surface_silver)):
        for other in (vix_bronze, vix_silver, option_bronze, surface_silver)[index + 1 :]:
            base.separate(source, other)
    policy, registered_at = _load_policy(target, policy_id)
    pairs = [
        replay_matched_pair(
            vix_bronze,
            vix_silver,
            option_bronze,
            surface_silver,
            request,
            max_pair_gap_seconds=policy.max_pair_gap_seconds,
            max_source_age_seconds=policy.max_source_age_seconds,
        )
        for request in requests
    ]
    pairs.sort(key=lambda item: item.as_of)
    evaluate_india_vix_iv30_proxy(
        pairs,
        max_pair_gap_seconds=policy.max_pair_gap_seconds,
        holdout_fraction=policy.holdout_fraction,
    )
    body = _canonical([asdict(pair) for pair in pairs])
    if len(body) > MAX_PAIRSET_BYTES:
        raise ValueError("PROXY_PAIRSET_BYTE_BOUND")
    pair_set_id = base.sha(_canonical(dict(policy_id=policy_id, pairs_sha256=base.sha(body))))
    table = _table(target, PAIRSETS)
    existing = target.execute(
        f"SELECT body,job_id FROM {table} WHERE pair_set_id=? LIMIT 2", [pair_set_id]
    ).fetchall()
    if existing:
        if len(existing) != 1 or bytes(existing[0][0]) != body:
            raise ValueError("PROXY_PAIRSET_RETRY_CONFLICT")
        vix.audit(target, existing[0][1], PAIRSET_COMMAND, pair_set_id, policy_id)
        return pair_set_id
    if registered_at > datetime.now(UTC):
        raise ValueError("POLICY_MUST_BE_PREREGISTERED")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=PAIRSET_COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref=pair_set_id,
        config_hash=policy_id,
    )
    with ledger.execution(job):
        target.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?)",
            [pair_set_id, policy_id, body, datetime.now(UTC), job],
        )
    return pair_set_id


def _load_pair_set(conn: Any, pair_set_id: str) -> tuple[list[ProxyPair], str, datetime]:
    if not _pin(pair_set_id):
        raise ValueError("EXACT_PROXY_PAIRSET_PIN_REQUIRED")
    rows = conn.execute(
        f"SELECT policy_id,body,recorded_at,job_id FROM {_table(conn, PAIRSETS)} "
        "WHERE pair_set_id=? LIMIT 2",
        [pair_set_id],
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("PROXY_PAIRSET_NOT_FOUND")
    policy_id, raw_value, recorded_at, job = rows[0]
    raw = bytes(raw_value)
    if base.sha(_canonical(dict(policy_id=policy_id, pairs_sha256=base.sha(raw)))) != pair_set_id:
        raise ValueError("PROXY_PAIRSET_IDENTITY_MISMATCH")
    vix.audit(conn, job, PAIRSET_COMMAND, pair_set_id, policy_id)
    docs = json.loads(raw)
    pairs = []
    for doc in docs:
        doc["trade_date"] = date.fromisoformat(doc["trade_date"])
        for field in (
            "as_of",
            "india_vix_source_time",
            "india_vix_received_at",
            "surface_source_time",
            "surface_received_at",
            "vix_available_at",
            "surface_available_at",
        ):
            if doc.get(field) is not None:
                doc[field] = _utc(doc[field])
        doc["condition_tags"] = tuple(doc.get("condition_tags", ()))
        pairs.append(ProxyPair(**doc))
    return pairs, policy_id, _utc(recorded_at)


def _criteria(metrics: dict[str, Any], policy: ProxyAcceptancePolicy) -> dict[str, bool]:
    correlation = metrics.get("correlation")
    slope = metrics.get("ols_slope_vix_on_surface")
    return {
        "absolute_bias": abs(metrics["bias_vix_minus_surface"]) <= policy.max_abs_bias,
        "mae": metrics["mae"] <= policy.max_mae,
        "rmse": metrics["rmse"] <= policy.max_rmse,
        "p90_absolute_error": metrics["p90_absolute_error"] <= policy.max_p90_absolute_error,
        "correlation": correlation is not None and correlation >= policy.min_correlation,
        "ols_slope": slope is not None and policy.min_ols_slope <= slope <= policy.max_ols_slope,
    }


def evaluate_pair_set(conn: Any, pair_set_id: str, *, actor_id: str, code_revision: str) -> dict[str, Any]:
    """Evaluate only a preregistered immutable pair set; report review status, never approval."""
    vix.execution(actor_id, code_revision)
    _file_backed(conn)
    vix.silver_target(conn)
    pairs, policy_id, pair_set_recorded_at = _load_pair_set(conn, pair_set_id)
    policy, policy_registered_at = _load_policy(conn, policy_id)
    if policy_registered_at > pair_set_recorded_at:
        raise ValueError("POLICY_NOT_PREREGISTERED_BEFORE_PAIRSET")
    result = evaluate_india_vix_iv30_proxy(
        pairs,
        max_pair_gap_seconds=policy.max_pair_gap_seconds,
        holdout_fraction=policy.holdout_fraction,
    )
    condition_results = {}
    sufficient_conditions = True
    all_conditions_pass = True
    for condition in policy.required_conditions:
        values = result["condition_metrics"].get(condition)
        if (
            values is None
            or values["holdout"] is None
            or values["holdout"]["pairs"] < policy.minimum_holdout_pairs_per_condition
        ):
            sufficient_conditions = False
            condition_results[condition] = dict(status="INSUFFICIENT_HOLDOUT_EVIDENCE", criteria=None)
            continue
        criteria = _criteria(values["holdout"], policy)
        passed = all(criteria.values())
        all_conditions_pass = all_conditions_pass and passed
        condition_results[condition] = dict(
            status="CRITERIA_MET_REVIEW_REQUIRED" if passed else "CRITERIA_NOT_MET_REVIEW_REQUIRED",
            criteria=criteria,
            holdout_metrics=values["holdout"],
            holdout_sessions=values["holdout_sessions"],
        )
    overall_criteria = (
        _criteria(result["holdout_metrics"], policy)
        if result["sample"]["holdout_pairs"] >= 20
        else None
    )
    if (
        result["assessment_status"] == "INSUFFICIENT_EVIDENCE"
        or not sufficient_conditions
        or overall_criteria is None
    ):
        status = "INSUFFICIENT_EVIDENCE"
    elif not all(overall_criteria.values()) or not all_conditions_pass:
        status = "HOLDOUT_CRITERIA_NOT_MET_REVIEW_REQUIRED"
    else:
        status = "HOLDOUT_CRITERIA_MET_REVIEW_REQUIRED"
    report = dict(
        version=VERSION,
        pair_set_id=pair_set_id,
        preregistered_policy_id=policy_id,
        policy_registered_at=policy_registered_at.isoformat(),
        pair_set_recorded_at=pair_set_recorded_at.isoformat(),
        status=status,
        overall_holdout_criteria=overall_criteria,
        condition_results=condition_results,
        diagnostics=result,
        pair_source_replay_verified_at_pairset_creation=True,
        pair_source_availability_verified_at_pairset_creation=True,
        atomic_cross_database_snapshot_asserted=False,
        external_source_authenticity_asserted=False,
        suitability_asserted=False,
        decision_eligibility_asserted=False,
        publication_asserted=False,
        model_suitability_verified=False,
        human_review_required=True,
    )
    return report


def persist_evaluation_report(
    conn: Any,
    pair_set_id: str,
    *,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    _file_backed(conn)
    vix.silver_target(conn)
    report = evaluate_pair_set(conn, pair_set_id, actor_id=actor_id, code_revision=code_revision)
    raw = _canonical(report)
    digest = base.sha(raw)
    table = _table(conn, REPORTS)
    variants = conn.execute(
        f"SELECT report_sha256,body,job_id FROM {table} WHERE pair_set_id=? LIMIT 2", [pair_set_id]
    ).fetchall()
    if variants:
        if len(variants) != 1 or variants[0][0] != digest or bytes(variants[0][1]) != raw:
            raise ValueError("PROXY_REPORT_VARIANT_CONFLICT")
        vix.audit(conn, variants[0][2], REPORT_COMMAND, pair_set_id, digest)
        return report
    ledger = AuditLedger(conn)
    job = ledger.plan_job(
        command_name=REPORT_COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref=pair_set_id,
        config_hash=digest,
    )
    with ledger.execution(job):
        conn.execute(f"INSERT INTO {table} VALUES (?,?,?,?)", [pair_set_id, digest, raw, job])
    return report


def replay_pair_set(
    vix_bronze: Any,
    vix_silver: Any,
    option_bronze: Any,
    surface_silver: Any,
    reader: Any,
    pair_set_id: str,
) -> list[ProxyPair]:
    """Rebuild every pair from its original pinned sources and compare the immutable pair set."""
    sources = (vix_bronze, vix_silver, option_bronze, surface_silver)
    for source in sources:
        _file_backed(source)
        base.readonly(source)
        base.separate(source, reader)
    for index, source in enumerate(sources):
        for other in sources[index + 1 :]:
            base.separate(source, other)
    _file_backed(reader)
    base.readonly(reader)
    vix.silver_target(reader)
    stored, policy_id, pair_set_recorded_at = _load_pair_set(reader, pair_set_id)
    policy, registered_at = _load_policy(reader, policy_id)
    if registered_at > pair_set_recorded_at:
        raise ValueError("POLICY_NOT_PREREGISTERED_BEFORE_PAIRSET")
    reproduced = []
    for pair in stored:
        if pair.condition_evidence_json is None or pair.condition_evidence_sha256 is None:
            raise ValueError("RETAINED_CONDITION_EVIDENCE_REQUIRED")
        request = ProxyPairRequest(
            vix_silver_revision_id=pair.vix_silver_revision_id,
            surface_observation_id=pair.surface_observation_id,
            surface_sha256=pair.surface_batch_sha256,
            condition_artifact=pair.condition_evidence_json.encode(),
            condition_sha256=pair.condition_evidence_sha256,
        )
        reproduced.append(
            replay_matched_pair(
                vix_bronze,
                vix_silver,
                option_bronze,
                surface_silver,
                request,
                max_pair_gap_seconds=policy.max_pair_gap_seconds,
                max_source_age_seconds=policy.max_source_age_seconds,
            )
        )
    reproduced.sort(key=lambda item: item.as_of)
    if _canonical([asdict(item) for item in reproduced]) != _canonical([asdict(item) for item in stored]):
        raise ValueError("PROXY_PAIRSET_SOURCE_REPLAY_MISMATCH")
    return reproduced


def replay_evaluation_report(
    conn: Any,
    pair_set_id: str,
    expected_report_sha256: str,
    *,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Read-only report replay: verify its audit, then recompute from the pinned pair set."""
    vix.execution(actor_id, code_revision)
    _file_backed(conn)
    base.readonly(conn)
    vix.silver_target(conn)
    if not _pin(expected_report_sha256):
        raise ValueError("EXACT_PROXY_REPORT_PIN_REQUIRED")
    rows = conn.execute(
        f"SELECT report_sha256,body,job_id FROM {_table(conn, REPORTS)} "
        "WHERE pair_set_id=? LIMIT 2",
        [pair_set_id],
    ).fetchall()
    if len(rows) != 1 or rows[0][0] != expected_report_sha256:
        raise ValueError("PROXY_REPORT_MISSING_CONFLICTED_OR_WRONG_PIN")
    raw = bytes(rows[0][1])
    if base.sha(raw) != expected_report_sha256:
        raise ValueError("PROXY_REPORT_HASH_MISMATCH")
    vix.audit(conn, rows[0][2], REPORT_COMMAND, pair_set_id, expected_report_sha256)
    reproduced = evaluate_pair_set(conn, pair_set_id, actor_id=actor_id, code_revision=code_revision)
    if _canonical(reproduced) != raw:
        raise ValueError("PROXY_REPORT_REPLAY_MISMATCH")
    return reproduced
