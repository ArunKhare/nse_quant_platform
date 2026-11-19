"""Repository integration: actual stage/audit/files, existing synthetic source boundary.

Not executed in delivery sandbox. Not acquisition-native E2E.
"""

import hashlib
from dataclasses import asdict

import pytest
from test_research_iv_current_stage_boundary import (
    archive_case as archive_case,
)
from test_research_iv_current_stage_boundary import (
    artifact_case as artifact_case,
)
from test_research_iv_current_stage_boundary import (
    bundle_case as bundle_case,
)
from test_research_iv_current_stage_boundary import (
    current_bundle_case as current_bundle_case,
)
from test_research_iv_current_stage_boundary import (
    current_stage_case as current_stage_case,
)
from test_research_iv_current_stage_boundary import (
    revalidation_case as revalidation_case,
)
from test_research_iv_current_stage_boundary import (
    scenario as scenario,
)
from test_research_iv_current_stage_boundary import (
    setup as setup,
)
from test_research_iv_current_stage_boundary import (
    stage_case as stage_case,
)
from test_research_iv_current_stage_boundary import (
    writer as writer,
)

from nse_quant.data_platform import research_iv_artifact_inventory as inventory
from nse_quant.data_platform import research_iv_first_stage as store
from nse_quant.data_platform import research_iv_recovery_plan as service


def plan(case, **changes):
    _, staging, receipt, reviewed, root, _ = case
    kwargs = dict(
        stage_build_id_pin=receipt["build_id"],
        expected_stage_fingerprint=reviewed.evidence_fingerprint,
        artifact_root=root,
    )
    kwargs.update(changes)
    return service.plan_research_iv_stage_recovery(staging, **kwargs)


def test_actual_stage_reconciles_without_authorizing_recovery(current_stage_case):
    value = plan(current_stage_case)
    assert value.status == "reconciled_retain_only"
    assert len(value.entries) == 1
    assert value.entries[0].disposition == "RECORDED_ARTIFACT_RETAIN"
    for field in (
        "current_source_checked",
        "orphan_status_determined",
        "destructive_actions_authorized",
        "adoption_authorized",
        "retry_authorized",
        "recovery_execution_authorized",
        "publication_asserted",
        "decision_eligibility_asserted",
    ):
        assert asdict(value)[field] is False
    assert value == plan(current_stage_case)


def test_unreviewed_pin_stops_before_inventory(current_stage_case, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unreviewed stage reached inventory")

    monkeypatch.setattr(inventory, "inventory_research_iv_artifacts", forbidden)
    with pytest.raises(ValueError, match="EXACT_REVIEWED_STAGE"):
        plan(current_stage_case, expected_stage_fingerprint="0" * 64)


def test_foreign_file_blocks_stage_read_without_cleanup(current_stage_case):
    root = current_stage_case[4]
    foreign = root / "private-name.txt"
    foreign.write_bytes(b"retain")
    with pytest.raises(ValueError, match="ROOT_CONTENT_REQUIRES_REVIEW"):
        plan(current_stage_case)
    assert foreign.read_bytes() == b"retain"


def test_inventory_exception_has_no_partial_plan(current_stage_case, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("synthetic boundary failure")

    monkeypatch.setattr(inventory, "inventory_research_iv_artifacts", fail)
    with pytest.raises(OSError, match="synthetic boundary failure"):
        plan(current_stage_case)


def test_stage_metadata_drift_requires_review(current_stage_case, monkeypatch):
    staging = current_stage_case[1]
    real = inventory.inventory_research_iv_artifacts
    calls = 0

    def observe(root):
        nonlocal calls
        value = real(root)
        calls += 1
        if calls == 2:
            table = store._name(staging, "gold", store.TABLES[1])
            staging.execute(f"UPDATE {table} SET recorded_at=recorded_at+INTERVAL '1 second'")
        return value

    monkeypatch.setattr(inventory, "inventory_research_iv_artifacts", observe)
    value = plan(current_stage_case)
    assert calls == 2 and value.status == "review_required"
    assert "IV_RECOVERY_EVIDENCE_CHANGED" in value.reason_codes


def test_extra_matching_bytes_are_not_adopted(current_stage_case):
    root = current_stage_case[4]
    raw = b"synthetic matching bytes, not canonical bundle proof"
    path = root / (hashlib.sha256(raw).hexdigest() + ".research-iv.json")
    path.write_bytes(raw)
    value = plan(current_stage_case)
    assert value.status == "review_required"
    assert any(e.disposition == "OUTSIDE_REVIEWED_BINDING_OWNERSHIP_UNKNOWN" for e in value.entries)
    assert path.read_bytes() == raw
    assert not value.adoption_authorized


def test_reconciliation_does_not_write_stage_tables(current_stage_case):
    staging = current_stage_case[1]
    names = [store._name(staging, "gold", name) for name in store.TABLES]
    names.extend(
        store._name(staging, "medallion_audit", name)
        for name in ("dataset_contracts", "jobs", "job_events")
    )
    before = [staging.execute(f"SELECT * FROM {name} ORDER BY ALL").fetchall() for name in names]
    assert plan(current_stage_case).status == "reconciled_retain_only"
    after = [staging.execute(f"SELECT * FROM {name} ORDER BY ALL").fetchall() for name in names]
    assert before == after
