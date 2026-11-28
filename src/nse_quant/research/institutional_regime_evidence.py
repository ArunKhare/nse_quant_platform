"""Build content-addressed, research-only evidence bundles from pinned regime observations.

The decision loop remains the sole writer of operational decision evidence. This
module is an offline, read-only research consumer: it assembles exact persisted
evidence pins into a reproducible review artifact without changing Gold
publication, strategy eligibility, paper-trading, or execution authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.core.regime_registry import (
    REGIME_REGISTRY_VERSION,
    is_canonical_regime_label,
)

ARTIFACT_NAME = "institutional_regime_research_evidence"
ARTIFACT_VERSION = "institutional_regime_research_evidence@1"
PLUGIN_NAME = "institutional_regime"


class EvidenceBundleRejected(ValueError):
    """A source row violates the pinned evidence or point-in-time contract."""


def _utc(value: object, *, field: str, naive_is_utc: bool = False) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise EvidenceBundleRejected(f"{field}_INVALID_TIMESTAMP") from exc
    if not isinstance(value, datetime):
        raise EvidenceBundleRejected(f"{field}_TIMESTAMP_REQUIRED")
    if value.tzinfo is None or value.utcoffset() is None:
        if not naive_is_utc:
            raise EvidenceBundleRejected(f"{field}_AWARE_TIMESTAMP_REQUIRED")
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _decode_payload(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise EvidenceBundleRejected("PAYLOAD_JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise EvidenceBundleRejected("PAYLOAD_OBJECT_REQUIRED")
    return value


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceBundleRejected("BUNDLE_NOT_CANONICAL_JSON") from exc


def _normalize_observation(
    row: Mapping[str, Any],
    *,
    symbol: str,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    required = {"evidence_id", "run_id", "ts", "symbol", "available"}
    if not required.issubset(row) or not ({"payload_json", "payload"} & set(row)):
        raise EvidenceBundleRejected("DECISION_EVIDENCE_FIELDS_REQUIRED")

    evidence_id = row["evidence_id"]
    run_id = row["run_id"]
    row_symbol = row["symbol"]
    if not isinstance(evidence_id, str) or not evidence_id.strip():
        raise EvidenceBundleRejected("EXACT_EVIDENCE_PIN_REQUIRED")
    if not isinstance(run_id, str) or not run_id.strip():
        raise EvidenceBundleRejected("RUN_ID_REQUIRED")
    if row_symbol != symbol:
        raise EvidenceBundleRejected("EVIDENCE_SYMBOL_MISMATCH")

    # decision_evidence.ts is a timezone-naive DuckDB TIMESTAMP. The operational
    # writer supplies UTC-aware DecisionContext timestamps; interpret the stored
    # value as UTC when reconstructing its instant.
    observed_at = _utc(row["ts"], field="decision_evidence.ts", naive_is_utc=True)
    if observed_at < start or observed_at >= end:
        raise EvidenceBundleRejected("EVIDENCE_OUTSIDE_REQUESTED_WINDOW")

    payload = _decode_payload(row.get("payload_json", row.get("payload")))
    if payload.get("symbol") != symbol:
        raise EvidenceBundleRejected("PAYLOAD_SYMBOL_MISMATCH")
    as_of = _utc(payload.get("as_of"), field="payload.as_of")
    if as_of > observed_at:
        raise EvidenceBundleRejected("FUTURE_EVIDENCE_INPUT")
    if as_of < start or as_of >= end:
        raise EvidenceBundleRejected("PAYLOAD_OUTSIDE_REQUESTED_WINDOW")

    if row["available"] != payload.get("available"):
        raise EvidenceBundleRejected("AVAILABILITY_ENVELOPE_MISMATCH")
    if payload.get("thresholds_provisional") is not True:
        raise EvidenceBundleRejected("PROVISIONAL_THRESHOLD_FLAG_REQUIRED")
    if payload.get("decision_eligibility_asserted") is not False:
        raise EvidenceBundleRejected("DECISION_ELIGIBILITY_MUST_REMAIN_FALSE")
    if payload.get("eligibility_approved") is not False:
        raise EvidenceBundleRejected("ELIGIBILITY_APPROVAL_MUST_REMAIN_FALSE")
    if payload.get("research_only") is not True:
        raise EvidenceBundleRejected("RESEARCH_ONLY_FLAG_REQUIRED")
    if payload.get("mode") != "observation":
        raise EvidenceBundleRejected("OBSERVATION_MODE_REQUIRED")

    components = payload.get("components")
    if not isinstance(components, dict):
        raise EvidenceBundleRejected("REGIME_COMPONENTS_REQUIRED")

    complete = payload.get("complete") is True
    label = payload.get("regime_label")
    label_valid = isinstance(label, str) and is_canonical_regime_label(label)
    if label is not None and not label_valid:
        raise EvidenceBundleRejected("NON_CANONICAL_REGIME_LABEL")
    if complete and payload.get("available") is not True:
        raise EvidenceBundleRejected("COMPLETE_EVIDENCE_REQUIRES_AVAILABLE_PAYLOAD")
    if complete and not label_valid:
        raise EvidenceBundleRejected("COMPLETE_EVIDENCE_REQUIRES_CANONICAL_LABEL")
    if label_valid and not complete:
        raise EvidenceBundleRejected("INCOMPLETE_EVIDENCE_CANNOT_CARRY_CANONICAL_LABEL")
    if label_valid and (
        payload.get("regime_vocabulary") != "canonical_v1"
        or payload.get("regime_version") != REGIME_REGISTRY_VERSION
    ):
        raise EvidenceBundleRejected("CANONICAL_REGIME_VERSION_MISMATCH")

    return {
        "evidence_id": evidence_id,
        "run_id": run_id,
        "ts": observed_at.isoformat(),
        "symbol": symbol,
        "available": row["available"] is True,
        "complete": complete,
        "regime_label": label if label_valid else None,
        "canonical_label_valid": label_valid,
        "classifier_version": payload.get("classifier_version"),
        "missing_components": list(payload.get("missing_components") or []),
        "reason": payload.get("reason"),
        "payload": payload,
    }


def load_institutional_regime_observations(
    connection: Any,
    *,
    symbol: str,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Read pinned regime observations from decision_evidence without writing."""
    start_utc = _utc(start, field="start")
    end_utc = _utc(end, field="end")
    if end_utc <= start_utc:
        raise EvidenceBundleRejected("INVALID_TIME_WINDOW")
    if not isinstance(symbol, str) or not symbol.strip():
        raise EvidenceBundleRejected("SYMBOL_REQUIRED")

    rows = connection.execute(
        """
        SELECT evidence_id, run_id, ts, symbol, available, payload_json
        FROM decision_evidence
        WHERE plugin = ?
          AND symbol = ?
          AND ts >= ?
          AND ts < ?
        ORDER BY ts, evidence_id
        """,
        [
            PLUGIN_NAME,
            symbol,
            start_utc.replace(tzinfo=None),
            end_utc.replace(tzinfo=None),
        ],
    ).fetchall()

    observations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for evidence_id, run_id, ts, row_symbol, available, payload_json in rows:
        normalized = _normalize_observation(
            {
                "evidence_id": evidence_id,
                "run_id": run_id,
                "ts": ts,
                "symbol": row_symbol,
                "available": available,
                "payload_json": payload_json,
            },
            symbol=symbol,
            start=start_utc,
            end=end_utc,
        )
        pin = normalized["evidence_id"]
        if pin in seen:
            raise EvidenceBundleRejected("DUPLICATE_EVIDENCE_PIN")
        seen.add(pin)
        observations.append(normalized)
    return observations


def build_institutional_regime_evidence_bundle(
    observations: Sequence[Mapping[str, Any]],
    *,
    symbol: str,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """Create a deterministic review bundle from exact persisted evidence pins."""
    start_utc = _utc(start, field="start")
    end_utc = _utc(end, field="end")
    if end_utc <= start_utc:
        raise EvidenceBundleRejected("INVALID_TIME_WINDOW")
    if not isinstance(symbol, str) or not symbol.strip():
        raise EvidenceBundleRejected("SYMBOL_REQUIRED")

    normalized = [
        _normalize_observation(
            row,
            symbol=symbol,
            start=start_utc,
            end=end_utc,
        )
        for row in observations
    ]
    normalized.sort(key=lambda item: (item["ts"], item["evidence_id"]))
    pins = [item["evidence_id"] for item in normalized]
    if len(pins) != len(set(pins)):
        raise EvidenceBundleRejected("DUPLICATE_EVIDENCE_PIN")
    if not normalized:
        raise EvidenceBundleRejected("NO_INSTITUTIONAL_REGIME_EVIDENCE")

    labels = Counter(
        item["regime_label"] for item in normalized if item["canonical_label_valid"]
    )
    classifier_versions = Counter(
        str(item["classifier_version"])
        for item in normalized
        if item["classifier_version"] is not None
    )
    source_vocabularies: Counter[str] = Counter()
    component_summary: dict[str, dict[str, Any]] = {}
    missing_components: Counter[str] = Counter()
    component_names = ("iv_state", "term_structure", "skew", "price_action")

    for item in normalized:
        for missing in item["missing_components"]:
            if isinstance(missing, str):
                missing_components[missing] += 1

    for component_name in component_names:
        available_count = 0
        complete_count = 0
        canonical_states: Counter[str] = Counter()
        source_states: Counter[str] = Counter()
        for item in normalized:
            component = item["payload"]["components"].get(component_name)
            if not isinstance(component, dict):
                continue
            if component.get("available") is True:
                available_count += 1
            if component.get("complete") is True:
                complete_count += 1
            source_state = component.get("source_state", component.get("state"))
            canonical_state = component.get("canonical_state")
            if isinstance(source_state, str):
                source_states[source_state] += 1
            if component.get("complete") is True and isinstance(canonical_state, str):
                canonical_states[canonical_state] += 1
            vocabulary = component.get("source_vocabulary")
            if isinstance(vocabulary, str):
                source_vocabularies[vocabulary] += 1
        component_summary[component_name] = {
            "available_count": available_count,
            "complete_count": complete_count,
            "availability_fraction": available_count / len(normalized),
            "completeness_fraction": complete_count / len(normalized),
            "source_state_counts": dict(sorted(source_states.items())),
            "canonical_state_counts": dict(sorted(canonical_states.items())),
        }

    available_count = sum(item["available"] for item in normalized)
    complete_count = sum(item["complete"] for item in normalized)
    canonical_count = sum(item["canonical_label_valid"] for item in normalized)
    first_observation = normalized[0]["ts"]
    last_observation = normalized[-1]["ts"]

    findings = [
        "PROVISIONAL_THRESHOLDS: all observations remain provisional",
        "RESEARCH_ONLY: no decision or execution authority is granted",
        "HUMAN_REVIEW_REQUIRED: this bundle is a review packet, not an approval",
    ]
    if source_vocabularies.get("v4_research", 0):
        findings.append(
            "V4_SEMANTICS_UNCALIBRATED: IV, term-structure and skew vocabulary "
            "normalization does not correct the v4 measurement methodology"
        )
    if complete_count < len(normalized):
        findings.append("INCOMPLETE_OBSERVATIONS_PRESENT: inspect missing-component coverage")
    if canonical_count == 0:
        findings.append("NO_COMPLETE_CANONICAL_REGIME_LABELS: no full four-axis label was observed")

    core: dict[str, Any] = {
        "artifact_name": ARTIFACT_NAME,
        "artifact_version": ARTIFACT_VERSION,
        "symbol": symbol,
        "market_as_of": last_observation,
        "source_data_range": {
            "start_inclusive": start_utc.isoformat(),
            "end_exclusive": end_utc.isoformat(),
            "first_observation": first_observation,
            "last_observation": last_observation,
        },
        "input_provenance": {
            "source_table": "decision_evidence",
            "plugin": PLUGIN_NAME,
            "evidence_ids": pins,
            "classifier_version_counts": dict(sorted(classifier_versions.items())),
            "source_vocabulary_counts": dict(sorted(source_vocabularies.items())),
            "regime_registry_version": REGIME_REGISTRY_VERSION,
        },
        "summary": {
            "observation_count": len(normalized),
            "available_count": available_count,
            "complete_count": complete_count,
            "incomplete_count": len(normalized) - complete_count,
            "canonical_label_count": canonical_count,
            "availability_fraction": available_count / len(normalized),
            "completeness_fraction": complete_count / len(normalized),
            "canonical_label_fraction": canonical_count / len(normalized),
            "canonical_label_counts": dict(sorted(labels.items())),
            "missing_component_counts": dict(sorted(missing_components.items())),
            "components": component_summary,
        },
        "observations": normalized,
        "review": {
            "review_status": "PENDING_HUMAN_REVIEW",
            "findings": findings,
            "recommendation": "RESEARCH_REVIEW_ONLY",
        },
        "publication": {
            "artifact_status": "CANDIDATE_NOT_PUBLISHED",
            "published_at": None,
            "gold_admission_asserted": False,
        },
        "governance": {
            "thresholds_provisional": True,
            "research_only": True,
            "eligibility_approved": False,
            "decision_eligibility_asserted": False,
            "paper_trading_approval_asserted": False,
            "live_trading_approval_asserted": False,
        },
    }
    digest = hashlib.sha256(_canonical_json(core).encode("utf-8")).hexdigest()
    return {
        **core,
        "bundle_id": f"irb_{digest}",
        "content_sha256": digest,
    }


def render_institutional_regime_evidence_review(bundle: Mapping[str, Any]) -> str:
    """Render a concise, human-reviewable report for a pinned evidence bundle."""
    summary = bundle["summary"]
    lines = [
        "# Institutional Regime Research Evidence Review",
        "",
        f"- Bundle ID: `{bundle['bundle_id']}`",
        f"- Content SHA-256: `{bundle['content_sha256']}`",
        f"- Artifact: `{bundle['artifact_name']} / {bundle['artifact_version']}`",
        f"- Symbol: {bundle['symbol']}",
        f"- Observation range: {bundle['source_data_range']['first_observation']} to "
        f"{bundle['source_data_range']['last_observation']}",
        f"- Review status: **{bundle['review']['review_status']}**",
        "",
        "## Coverage",
        "",
        "| Measure | Count | Fraction |",
        "|---|---:|---:|",
        f"| Observations | {summary['observation_count']} | 1.000 |",
        f"| Available | {summary['available_count']} | {summary['availability_fraction']:.3f} |",
        f"| Complete | {summary['complete_count']} | {summary['completeness_fraction']:.3f} |",
        f"| Canonical four-axis labels | {summary['canonical_label_count']} | "
        f"{summary['canonical_label_fraction']:.3f} |",
        "",
        "## Canonical regime labels",
        "",
    ]
    labels = summary["canonical_label_counts"]
    if labels:
        lines.extend(f"- `{label}`: {count}" for label, count in labels.items())
    else:
        lines.append("- No complete canonical regime labels in this window.")
    lines.extend(["", "## Component coverage", ""])
    for name, component in summary["components"].items():
        lines.append(
            f"- **{name}** — available {component['available_count']}/"
            f"{summary['observation_count']}; complete {component['complete_count']}/"
            f"{summary['observation_count']}"
        )
        lines.append(f"  - Source states: {component['source_state_counts']}")
        lines.append(f"  - Canonical states: {component['canonical_state_counts']}")
    lines.extend(["", "## Review findings", ""])
    lines.extend(f"- {finding}" for finding in bundle["review"]["findings"])
    lines.extend(
        [
            "",
            "## Governance boundary",
            "",
            "This is a content-addressed research review candidate assembled from exact "
            "decision-evidence pins. It is not a published Gold artifact, calibrated "
            "regime approval, strategy eligibility decision, paper-trading approval, "
            "or live-trading authorization. No threshold or runtime mode is promoted.",
            "",
        ]
    )
    return "\n".join(lines)


def write_institutional_regime_evidence_bundle(
    bundle: Mapping[str, Any],
    *,
    json_path: Path,
    markdown_path: Path,
) -> None:
    """Atomically write the JSON bundle and its review report."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    outputs = (
        (json_path, _canonical_json(bundle) + "\n"),
        (markdown_path, render_institutional_regime_evidence_review(bundle)),
    )
    for path, content in outputs:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
