"""Tests for research lifecycle/recovery classification."""

from __future__ import annotations

import pytest

from nse_quant.research.research_lifecycle_recovery import (
    ObligationState,
    classify_obligation,
)


def test_failed_not_healable():
    result = classify_obligation(
        obligation=dict(obligation_id="o1", status="FAILED", linked=True, result="x")
    )
    assert result.state == ObligationState.FAILED
    assert result.healable is False


def test_incomplete_not_healable():
    result = classify_obligation(
        obligation=dict(obligation_id="o2", status="INCOMPLETE", linked=True, result=None)
    )
    assert result.state == ObligationState.INCOMPLETE
    assert result.healable is False


def test_orphan_not_healable():
    result = classify_obligation(
        obligation=dict(obligation_id="o3", status="RESOLVED", linked=False, result="x")
    )
    assert result.state == ObligationState.ORPHAN
    assert result.healable is False


def test_unlinked_not_healable():
    result = classify_obligation(
        obligation=dict(obligation_id="o4", status="PENDING", linked=False, result=None)
    )
    assert result.state == ObligationState.UNLINKED
    assert result.healable is False


def test_pending_healable():
    result = classify_obligation(
        obligation=dict(obligation_id="o5", status="PENDING", linked=True, result=None)
    )
    assert result.state == ObligationState.PENDING
    assert result.healable is True


def test_resolved_healable():
    result = classify_obligation(
        obligation=dict(obligation_id="o6", status="RESOLVED", linked=True, result="x")
    )
    assert result.state == ObligationState.RESOLVED
    assert result.healable is True


def test_missing_id_refused():
    with pytest.raises(ValueError, match="OBLIGATION_ID_REQUIRED"):
        classify_obligation(obligation=dict(status="PENDING"))


def test_non_dict_refused():
    with pytest.raises(ValueError, match="OBJECT_REQUIRED"):
        classify_obligation(obligation="not_a_dict")
