"""A2 unit tests; the ledger protocol is tested with a recording double."""

import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from nse_quant.data_platform.commands import (
    Category,
    CommandDefinition,
    CommandRegistry,
    CommandResult,
)
from nse_quant.data_platform.manifests import ManifestStore, digest
from nse_quant.data_platform.runner import CommandRunner
from nse_quant.data_platform.scopes import ExecutionScope


class RecordingLedger:
    def __init__(self):
        self.events = []
        self.plans = []

    def plan_job(self, **kwargs):
        self.plans.append(kwargs)
        return f"job-{len(self.plans)}"

    @contextmanager
    def execution(self, job_id):
        self.events.append((job_id, "RUNNING"))
        try:
            yield job_id
        except BaseException:
            self.events.append((job_id, "FAILED"))
            raise
        else:
            self.events.append((job_id, "SUCCEEDED"))


def scope():
    return ExecutionScope(
        symbols=("NIFTY",),
        start=datetime(2026, 10, 30, tzinfo=UTC),
        end=datetime(2026, 10, 31, tzinfo=UTC),
        input_snapshot_refs=("snapshot-1",),
    )


def definition():
    return CommandDefinition(
        name="features.example",
        version="1",
        category=Category.BUILD,
        owner="research",
        reads=("silver.option_quotes",),
        writes=("gold.example",),
    )


def setup_runner(tmp_path, executor=None):
    registry = CommandRegistry()
    callback = (
        executor
        if executor is not None
        else Mock(
            return_value=CommandResult(
                rows_read=2,
                rows_written=1,
                output_refs=("build-1",),
            )
        )
    )
    registry.register(definition(), callback)
    ledger = RecordingLedger()
    runner = CommandRunner(registry, ManifestStore(tmp_path / "manifests"), ledger)
    return runner, ledger, callback


def execute(runner, **kwargs):
    values = dict(
        name="features.example",
        version="1",
        scope=scope(),
        actor_id="developer",
        code_revision="commit-1",
        config_hash="config-hash-1",
    )
    values.update(kwargs)
    return runner.run(**values)


def test_dry_run_has_no_audit_files_or_callback(tmp_path):
    runner, ledger, callback = setup_runner(tmp_path)
    report = execute(runner)
    assert report.job_id is None and report.result_id is None
    assert not (tmp_path / "manifests").exists()
    assert ledger.events == [] and ledger.plans == []
    callback.assert_not_called()
    assert json.loads(report.plan_json)["scope"]["end_exclusive"].startswith("2026-10-31")


def test_success_plan_receipt_and_parent(tmp_path):
    runner, ledger, callback = setup_runner(tmp_path)
    report = execute(runner, dry_run=False, parent_job_id="parent-1")
    assert report.job_id == "job-1"
    assert report.result_id is not None
    receipt = json.loads(runner.manifests.read(report.result_id))
    assert receipt["plan_id"] == report.plan_id
    assert receipt["result"]["rows_written"] == 1
    assert ledger.plans[0]["parent_job_id"] == "parent-1"
    assert ledger.plans[0]["scope_ref"] == "sha256:" + report.plan_id
    assert ledger.events == [("job-1", "RUNNING"), ("job-1", "SUCCEEDED")]
    callback.assert_called_once_with(scope())


def test_failure_audited_no_receipt(tmp_path):
    callback = Mock(side_effect=RuntimeError("domain failure"))
    runner, ledger, _ = setup_runner(tmp_path, callback)
    with pytest.raises(RuntimeError, match="domain failure"):
        execute(runner, dry_run=False)
    assert ledger.events[-1] == ("job-1", "FAILED")
    assert len(list((tmp_path / "manifests").glob("*.json"))) == 1


def test_non_result_return_is_failure(tmp_path):
    runner, ledger, _ = setup_runner(tmp_path, Mock(return_value=1))
    with pytest.raises(TypeError, match="CommandResult"):
        execute(runner, dry_run=False)
    assert ledger.events[-1][1] == "FAILED"


def test_registry_retry_conflict_and_unknown():
    registry = CommandRegistry()
    callback = Mock()
    assert registry.register(definition(), callback)
    assert not registry.register(definition(), callback)
    with pytest.raises(ValueError, match="another"):
        registry.register(definition(), Mock())
    with pytest.raises(ValueError, match="another"):
        registry.register(replace(definition(), owner="new"), callback)
    with pytest.raises(ValueError, match="Unregistered"):
        registry.resolve("missing", "1")


@pytest.mark.parametrize(
    "changes",
    [
        {"writes": ("bronze.option_events",)},
        {"reads": ("bronze.option_events",)},
        {"writes": ()},
        {"reads": ()},
        {"reads": ("silver.bad-name",)},
        {"writes": ("gold.example", "gold.example")},
    ],
)
def test_invalid_command_boundaries(changes):
    with pytest.raises(ValueError):
        replace(definition(), **changes)


def test_inspect_and_workflow_cannot_declare_domain_writes():
    with pytest.raises(ValueError):
        replace(definition(), category=Category.INSPECT)
    with pytest.raises(ValueError):
        replace(definition(), category=Category.WORKFLOW)


def test_ingest_and_normalize_valid_boundaries():
    CommandDefinition("ingest.test", "1", Category.INGEST, "capture", writes=("bronze.events",))
    CommandDefinition(
        "normalize.test",
        "1",
        Category.NORMALIZE,
        "capture",
        reads=("bronze.events",),
        writes=("silver.events",),
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"symbols": ()},
        {"symbols": ("nifty",)},
        {"symbols": ("NIFTY", "NIFTY")},
        {"start": datetime(2026, 10, 30)},
        {"end": datetime(2026, 10, 29, tzinfo=UTC)},
        {"run_ids": ("",)},
    ],
)
def test_invalid_scopes(changes):
    with pytest.raises(ValueError):
        replace(scope(), **changes)


def test_scope_equivalent_timezones_are_canonical():
    ist = timezone(timedelta(hours=5, minutes=30))
    original = scope()
    converted = replace(
        original, start=original.start.astimezone(ist), end=original.end.astimezone(ist)
    )
    assert converted.as_dict() == original.as_dict()


def test_missing_snapshot_fails_before_side_effects(tmp_path):
    runner, ledger, callback = setup_runner(tmp_path)
    with pytest.raises(ValueError, match="snapshot"):
        execute(runner, scope=replace(scope(), input_snapshot_refs=()), dry_run=False)
    assert ledger.plans == []
    assert not (tmp_path / "manifests").exists()
    callback.assert_not_called()


def test_manifest_exact_retry_and_tamper_detection(tmp_path):
    store = ManifestStore(tmp_path / "manifests")
    payload = b'{"test":1}'
    path = store.put(payload)
    assert store.put(payload) == path
    assert len(list(path.parent.glob("*.json"))) == 1
    assert store.read(digest(payload)) == payload
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        store.read(digest(payload))
    with pytest.raises(ValueError, match="conflicts"):
        store.put(payload)
    assert path.read_bytes() == b"tampered"
    assert list(path.parent.glob(".pending-*")) == []


def test_manifest_link_failure_has_no_final_file(tmp_path, monkeypatch):
    import os

    store = ManifestStore(tmp_path / "manifests")

    def fail_link(*args):
        raise OSError("link unsupported")

    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(OSError, match="unsupported"):
        store.put(b"{}")
    assert list(store.root.iterdir()) == []


def test_result_validation():
    with pytest.raises(ValueError):
        CommandResult(rows_written=-1)
    with pytest.raises(ValueError):
        CommandResult(rows_read=True)
    with pytest.raises(ValueError):
        CommandResult(output_refs=("",))


def test_result_manifest_failure_marks_job_failed(tmp_path, monkeypatch):
    runner, ledger, _ = setup_runner(tmp_path)
    original = runner.manifests.put
    calls = 0

    def fail_second(payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("receipt unavailable")
        return original(payload)

    monkeypatch.setattr(runner.manifests, "put", fail_second)
    with pytest.raises(OSError, match="receipt"):
        execute(runner, dry_run=False)
    assert ledger.events[-1][1] == "FAILED"


def test_empty_output_requires_explicit_reference(tmp_path):
    runner, ledger, _ = setup_runner(tmp_path, Mock(return_value=CommandResult()))
    with pytest.raises(ValueError, match="output"):
        execute(runner, dry_run=False)
    assert ledger.events[-1][1] == "FAILED"
