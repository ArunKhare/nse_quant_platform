"""Tests for institutional regime evidence persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from nse_quant.research.institutional_regime_persistence import (
    PersistenceRejected,
    evidence_id,
    initialize,
    persist_regime_evidence,
    read_regime_evidence,
)


def _payload():
    return dict(
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
        symbol="NIFTY",
        classifier_version="institutional_iv_term_components_v4",
        regime_label="HIGH_IV_CONTANGO_NORMAL_SKEW_RANGE_UPPER",
        complete=True,
        components={},
    )


def _target():
    class _Target:
        def __init__(self):
            self.rows = {}
            self.payload_json: str | None = None

        def execute(self, sql, params=None):
            if "CREATE TABLE" in sql:
                return None
            if "SELECT 1 FROM" in sql:
                key = params[0]
                return type("R", (), {"fetchone": lambda s: self.rows.get(key)})()
            if "INSERT INTO" in sql:
                self.rows[params[0]] = True
                self.payload_json = params[6]
                return None
            if "SELECT as_of" in sql:
                key = params[0]
                if key not in self.rows:
                    return type("R", (), {"fetchone": lambda s: None})()
                return type(
                    "R",
                    (),
                    {
                        "fetchone": lambda s: (
                            datetime(2026, 1, 1, tzinfo=UTC),
                            "NIFTY",
                            "institutional_iv_term_components_v4",
                            "HIGH_IV_CONTANGO_NORMAL_SKEW_RANGE_UPPER",
                            True,
                            "{}",
                            datetime(2026, 1, 1, tzinfo=UTC),
                        )
                    },
                )()
            return None

    return _Target()


def test_first_write_succeeds():
    target = _target()
    initialize(target)
    result = persist_regime_evidence(
        target, payload=_payload(), actor_id="reviewer", code_revision="a" * 40
    )
    assert result["decision_eligibility_asserted"] is False
    assert result["regime_label"] == "HIGH_IV_CONTANGO_NORMAL_SKEW_RANGE_UPPER"
    assert target.payload_json is not None
    assert json.loads(target.payload_json)["as_of"] == "2026-01-01T00:00:00+00:00"


def test_nested_datetimes_are_serialized_as_utc():
    target = _target()
    initialize(target)
    payload = _payload()
    payload["components"] = {"observed_at": datetime(2026, 1, 1, tzinfo=UTC)}

    persist_regime_evidence(target, payload=payload, actor_id="reviewer", code_revision="a" * 40)

    assert target.payload_json is not None
    assert json.loads(target.payload_json)["components"]["observed_at"] == (
        "2026-01-01T00:00:00+00:00"
    )


def test_second_write_refused():
    target = _target()
    initialize(target)
    persist_regime_evidence(target, payload=_payload(), actor_id="reviewer", code_revision="a" * 40)
    with pytest.raises(PersistenceRejected, match="FIRST_WRITE"):
        persist_regime_evidence(
            target, payload=_payload(), actor_id="reviewer", code_revision="a" * 40
        )


def test_read_roundtrip():
    target = _target()
    initialize(target)
    written = persist_regime_evidence(
        target, payload=_payload(), actor_id="reviewer", code_revision="a" * 40
    )
    read = read_regime_evidence(target, evidence_id=written["evidence_id"])
    assert read["regime_label"] == written["regime_label"]
    assert read["complete"] is True


def test_missing_payload_field_refused():
    target = _target()
    initialize(target)
    payload = _payload()
    del payload["regime_label"]
    with pytest.raises(PersistenceRejected, match="FIELDS_REQUIRED"):
        persist_regime_evidence(
            target, payload=payload, actor_id="reviewer", code_revision="a" * 40
        )


def test_bad_actor_refused():
    target = _target()
    initialize(target)
    with pytest.raises(PersistenceRejected, match="ACTOR"):
        persist_regime_evidence(target, payload=_payload(), actor_id="", code_revision="a" * 40)


def test_evidence_id_deterministic():
    a = evidence_id(
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
        symbol="NIFTY",
        classifier_version="v4",
    )
    b = evidence_id(
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
        symbol="NIFTY",
        classifier_version="v4",
    )
    assert a == b
