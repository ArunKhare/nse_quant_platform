from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.research.institutional_regime_evidence import (
    EvidenceBundleRejected,
    build_institutional_regime_evidence_bundle,
    load_institutional_regime_observations,
    write_institutional_regime_evidence_bundle,
)

TS = datetime(2026, 11, 28, 10, 0, tzinfo=UTC)
REGIME_LABEL = "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP"


def _payload(
    *,
    ts: datetime = TS,
    complete: bool = True,
    decision_eligibility_asserted: bool = False,
) -> dict[str, Any]:
    states = {
        "iv_state": ("HIGH_IV", "HIGH_IV", "v4_research"),
        "term_structure": ("CONTANGO", "CONTANGO", "v4_research"),
        "skew": ("NORMAL_SKEW", "NORMAL_SKEW", "v4_research"),
        "price_action": ("HIGH_VOL_CHOP", "HIGH_VOL_CHOP", "v5_price_action"),
    }
    components = {
        name: {
            "available": True,
            "complete": complete,
            "state": source_state,
            "source_state": source_state,
            "canonical_state": canonical_state if complete else None,
            "source_vocabulary": vocabulary,
            "research_only": True,
            "eligibility_approved": False,
        }
        for name, (source_state, canonical_state, vocabulary) in states.items()
    }
    return {
        "available": True,
        "complete": complete,
        "thresholds_provisional": True,
        "decision_eligibility_asserted": decision_eligibility_asserted,
        "eligibility_approved": False,
        "research_only": True,
        "mode": "observation",
        "as_of": ts.isoformat(),
        "symbol": "NIFTY",
        "classifier_version": "institutional_iv_term_components_v4_with_daily_price_action_v5",
        "regime_vocabulary": "canonical_v1" if complete else None,
        "regime_version": "institutional_regime_registry_v2" if complete else None,
        "regime_label": REGIME_LABEL if complete else None,
        "components": components,
        "missing_components": [] if complete else ["term_structure"],
        "reason": None if complete else "missing_term_structure",
    }


def _row(
    *,
    evidence_id: str = "pin-001",
    ts: datetime = TS,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = payload or _payload(ts=ts)
    return {
        "evidence_id": evidence_id,
        "run_id": "paper-run-001",
        "ts": ts,
        "symbol": "NIFTY",
        "available": value["available"],
        "payload": value,
    }


def test_bundle_contains_exact_pins_provenance_and_research_boundary() -> None:
    rows = [_row(), _row(evidence_id="pin-002", ts=TS + timedelta(minutes=1))]
    bundle = build_institutional_regime_evidence_bundle(
        rows,
        symbol="NIFTY",
        start=TS - timedelta(minutes=1),
        end=TS + timedelta(minutes=5),
    )

    assert bundle["input_provenance"]["evidence_ids"] == ["pin-001", "pin-002"]
    assert bundle["summary"]["observation_count"] == 2
    assert bundle["summary"]["complete_count"] == 2
    assert bundle["summary"]["canonical_label_count"] == 2
    assert bundle["summary"]["canonical_label_counts"] == {REGIME_LABEL: 2}
    assert bundle["governance"]["research_only"] is True
    assert bundle["governance"]["decision_eligibility_asserted"] is False
    assert bundle["governance"]["paper_trading_approval_asserted"] is False
    assert bundle["publication"]["artifact_status"] == "CANDIDATE_NOT_PUBLISHED"
    assert bundle["review"]["review_status"] == "PENDING_HUMAN_REVIEW"


def test_bundle_id_is_deterministic_and_independent_of_input_order() -> None:
    first = _row()
    second = _row(evidence_id="pin-002", ts=TS + timedelta(minutes=1))
    kwargs = {
        "symbol": "NIFTY",
        "start": TS - timedelta(minutes=1),
        "end": TS + timedelta(minutes=5),
    }

    left = build_institutional_regime_evidence_bundle([first, second], **kwargs)
    right = build_institutional_regime_evidence_bundle([second, first], **kwargs)

    assert left["bundle_id"] == right["bundle_id"]
    assert left["content_sha256"] == right["content_sha256"]


def test_incomplete_observations_are_retained_without_fabricating_a_label() -> None:
    incomplete = _row(
        payload=_payload(complete=False),
    )
    bundle = build_institutional_regime_evidence_bundle(
        [incomplete],
        symbol="NIFTY",
        start=TS - timedelta(minutes=1),
        end=TS + timedelta(minutes=1),
    )

    assert bundle["summary"]["incomplete_count"] == 1
    assert bundle["summary"]["canonical_label_count"] == 0
    assert bundle["summary"]["missing_component_counts"] == {"term_structure": 1}
    assert any("NO_COMPLETE_CANONICAL" in item for item in bundle["review"]["findings"])


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("decision_eligibility_asserted", True, "DECISION_ELIGIBILITY_MUST_REMAIN_FALSE"),
        ("eligibility_approved", True, "ELIGIBILITY_APPROVAL_MUST_REMAIN_FALSE"),
        ("research_only", False, "RESEARCH_ONLY_FLAG_REQUIRED"),
        ("thresholds_provisional", False, "PROVISIONAL_THRESHOLD_FLAG_REQUIRED"),
        ("mode", "hard_gate", "OBSERVATION_MODE_REQUIRED"),
    ],
)
def test_governance_boundary_is_enforced(field: str, value: Any, reason: str) -> None:
    payload = _payload()
    payload[field] = value

    with pytest.raises(EvidenceBundleRejected, match=reason):
        build_institutional_regime_evidence_bundle(
            [_row(payload=payload)],
            symbol="NIFTY",
            start=TS - timedelta(minutes=1),
            end=TS + timedelta(minutes=1),
        )


def test_future_as_of_is_rejected() -> None:
    payload = _payload(ts=TS + timedelta(minutes=1))

    with pytest.raises(EvidenceBundleRejected, match="FUTURE_EVIDENCE_INPUT"):
        build_institutional_regime_evidence_bundle(
            [_row(ts=TS, payload=payload)],
            symbol="NIFTY",
            start=TS - timedelta(minutes=1),
            end=TS + timedelta(minutes=2),
        )


def test_duplicate_evidence_pins_are_rejected() -> None:
    with pytest.raises(EvidenceBundleRejected, match="DUPLICATE_EVIDENCE_PIN"):
        build_institutional_regime_evidence_bundle(
            [_row(), _row()],
            symbol="NIFTY",
            start=TS - timedelta(minutes=1),
            end=TS + timedelta(minutes=1),
        )


def test_loader_reads_only_exact_plugin_symbol_and_half_open_window() -> None:
    connection = duckdb.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE decision_evidence (
            evidence_id TEXT,
            run_id TEXT,
            ts TIMESTAMP,
            symbol TEXT,
            plugin TEXT,
            available BOOLEAN,
            payload_json TEXT
        )
        """
    )
    payload = _payload()
    connection.execute(
        "INSERT INTO decision_evidence VALUES (?, ?, ?, ?, ?, ?, ?)",
        ["pin-001", "paper-run-001", TS.replace(tzinfo=None), "NIFTY",
         "institutional_regime", True, json.dumps(payload)],
    )
    connection.execute(
        "INSERT INTO decision_evidence VALUES (?, ?, ?, ?, ?, ?, ?)",
        ["pin-002", "paper-run-001", TS.replace(tzinfo=None), "NIFTY",
         "market_context", True, json.dumps(payload)],
    )
    connection.execute(
        "INSERT INTO decision_evidence VALUES (?, ?, ?, ?, ?, ?, ?)",
        ["pin-003", "paper-run-001", (TS + timedelta(minutes=1)).replace(tzinfo=None),
         "NIFTY", "institutional_regime", True, json.dumps(_payload(ts=TS + timedelta(minutes=1)))],
    )

    try:
        rows = load_institutional_regime_observations(
            connection,
            symbol="NIFTY",
            start=TS - timedelta(minutes=1),
            end=TS + timedelta(minutes=1),
        )
    finally:
        connection.close()

    assert [row["evidence_id"] for row in rows] == ["pin-001"]


def test_bundle_and_markdown_are_written_atomically(tmp_path: Path) -> None:
    bundle = build_institutional_regime_evidence_bundle(
        [_row()],
        symbol="NIFTY",
        start=TS - timedelta(minutes=1),
        end=TS + timedelta(minutes=1),
    )
    json_path = tmp_path / "research" / "regime_bundle.json"
    markdown_path = tmp_path / "research" / "regime_bundle.md"

    write_institutional_regime_evidence_bundle(
        bundle,
        json_path=json_path,
        markdown_path=markdown_path,
    )

    stored = json.loads(json_path.read_text(encoding="utf-8"))
    report = markdown_path.read_text(encoding="utf-8")
    assert stored["bundle_id"] == bundle["bundle_id"]
    assert "PENDING_HUMAN_REVIEW" in report
    assert "not a published Gold artifact" in report
    assert sorted(path.name for path in json_path.parent.iterdir()) == [
        "regime_bundle.json",
        "regime_bundle.md",
    ]
