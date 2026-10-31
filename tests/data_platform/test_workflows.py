"""A2b isolated orchestration tests using recording child/ledger collaborators."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

if TYPE_CHECKING:
    from nse_quant.data_platform.scopes import ExecutionScope

import pytest

from nse_quant.data_platform.workflows import (
    WorkflowDefinition,
    WorkflowFailed,
    WorkflowRunner,
    WorkflowStep,
)


@dataclass(frozen=True)
class TestScope:
    __test__ = False
    symbols: tuple[str, ...] = ("NIFTY",)

    def as_dict(self):
        return {"symbols": list(self.symbols)}


def scope_double() -> ExecutionScope:
    return cast("ExecutionScope", TestScope())


@dataclass(frozen=True)
class Report:
    plan_id: str
    job_id: str | None
    result_id: str | None
    plan_json: str


class Children:
    def __init__(self, failures=(), invalid=(), malformed=False):
        self.calls = []
        self.failures = failures
        self.invalid = invalid
        self.malformed = malformed

    def run(self, **kwargs):
        self.calls.append(kwargs)
        name = kwargs["name"]
        if kwargs["dry_run"]:
            if name in self.invalid:
                raise ValueError("invalid preflight")
            return Report("plan-" + name, None, None, json.dumps({"name": name}))
        if name in self.failures:
            raise RuntimeError("private credential should not enter receipt")
        if self.malformed:
            return Report("plan-" + name, None, None, "{}")
        return Report("plan-" + name, "job-" + name, "result-" + name, "{}")


class Ledger:
    def __init__(self):
        self.plans = []
        self.events = []

    def plan_job(self, **kwargs):
        self.plans.append(kwargs)
        return "parent-1"

    @contextmanager
    def execution(self, job_id):
        self.events.append("RUNNING")
        try:
            yield job_id
        except KeyboardInterrupt:
            self.events.append("CANCELLED")
            raise
        except BaseException:
            self.events.append("FAILED")
            raise
        else:
            self.events.append("SUCCEEDED")


class Manifests:
    def __init__(self):
        self.payloads = []

    def put(self, payload):
        self.payloads.append(payload)


def definition():
    return WorkflowDefinition(
        "workflow.example",
        "1",
        "ops",
        (
            WorkflowStep("first", "first", "1", scope_double()),
            WorkflowStep("optional", "optional", "1", scope_double(), required=False),
            WorkflowStep("last", "last", "1", scope_double()),
        ),
    )


def setup(children=None):
    child_runner = children if children is not None else Children()
    ledger = Ledger()
    manifests = Manifests()
    return WorkflowRunner(child_runner, ledger, manifests), child_runner, ledger, manifests


def execute(runner, workflow=None, **kwargs):
    return runner.run(
        workflow if workflow is not None else definition(),
        actor_id="qa",
        code_revision="commit-1",
        config_hash="config-1",
        **kwargs,
    )


def actual(children):
    return [call["name"] for call in children.calls if not call["dry_run"]]


def test_default_dry_run_is_side_effect_free():
    runner, children, ledger, manifests = setup()
    report = execute(runner)
    assert report.status == "PLANNED" and report.job_id is None
    assert len(children.calls) == 3 and actual(children) == []
    assert ledger.plans == [] and manifests.payloads == []


def test_success_links_children_and_receipt():
    runner, children, ledger, manifests = setup()
    report = execute(runner, dry_run=False, parent_job_id="root-1")
    assert report.status == "SUCCEEDED"
    assert actual(children) == ["first", "optional", "last"]
    assert all(
        call["parent_job_id"] == "parent-1" for call in children.calls if not call["dry_run"]
    )
    assert ledger.plans[0]["parent_job_id"] == "root-1"
    assert ledger.events == ["RUNNING", "SUCCEEDED"]
    receipt = json.loads(manifests.payloads[-1])
    assert receipt["steps"][0]["child_job_id"] == "job-first"
    assert receipt["steps"][0]["child_result_id"] == "result-first"


def test_required_failure_stops_and_records_not_run():
    runner, children, ledger, manifests = setup(Children(failures=("first",)))
    with pytest.raises(WorkflowFailed) as error:
        execute(runner, dry_run=False)
    assert actual(children) == ["first"]
    assert ledger.events[-1] == "FAILED"
    assert [item.status for item in error.value.report.outcomes] == ["FAILED", "NOT_RUN", "NOT_RUN"]
    assert isinstance(error.value.__cause__, RuntimeError)
    assert b"private credential" not in manifests.payloads[-1]


def test_optional_failure_continues_and_is_not_silent():
    runner, children, ledger, manifests = setup(Children(failures=("optional",)))
    report = execute(runner, dry_run=False)
    assert report.status == "SUCCEEDED_WITH_WARNINGS"
    assert actual(children) == ["first", "optional", "last"]
    assert ledger.events[-1] == "SUCCEEDED"
    assert report.outcomes[1].reason_code == "CHILD_EXECUTION_FAILED"
    assert json.loads(manifests.payloads[-1])["status"] == "SUCCEEDED_WITH_WARNINGS"


def test_all_preflight_before_any_actual_side_effect():
    runner, children, ledger, manifests = setup(Children(invalid=("last",)))
    with pytest.raises(ValueError, match="preflight"):
        execute(runner, dry_run=False)
    assert actual(children) == [] and ledger.plans == [] and manifests.payloads == []


def test_malformed_child_success_fails_required_step():
    runner, children, ledger, _ = setup(Children(malformed=True))
    with pytest.raises(WorkflowFailed):
        execute(runner, dry_run=False)
    assert actual(children) == ["first"] and ledger.events[-1] == "FAILED"


def test_manifest_failure_prevents_job_and_execution():
    runner, children, ledger, manifests = setup()
    manifests.put = Mock(side_effect=OSError("manifest unavailable"))
    with pytest.raises(OSError):
        execute(runner, dry_run=False)
    assert actual(children) == [] and ledger.plans == []


def test_failed_receipt_does_not_hide_original_child_failure():
    runner, _, ledger, manifests = setup(Children(failures=("first",)))
    original = manifests.put

    def put(payload):
        if json.loads(payload)["kind"] == "workflow_receipt":
            raise OSError("receipt failed")
        original(payload)

    manifests.put = put
    with pytest.raises(WorkflowFailed) as error:
        execute(runner, dry_run=False)
    assert error.value.report.receipt_id is None
    assert isinstance(error.value.__cause__, RuntimeError)
    assert ledger.events[-1] == "FAILED"


def test_success_receipt_failure_marks_parent_failed():
    runner, _, ledger, manifests = setup()
    original = manifests.put

    def put(payload):
        if json.loads(payload)["kind"] == "workflow_receipt":
            raise OSError("receipt failed")
        original(payload)

    manifests.put = put
    with pytest.raises(OSError, match="receipt"):
        execute(runner, dry_run=False)
    assert ledger.events[-1] == "FAILED"


def test_cancellation_propagates_without_later_steps():
    runner, children, ledger, _ = setup()
    original = children.run

    def run(**kwargs):
        if not kwargs["dry_run"]:
            raise KeyboardInterrupt()
        return original(**kwargs)

    children.run = run
    with pytest.raises(KeyboardInterrupt):
        execute(runner, dry_run=False)
    assert ledger.events[-1] == "CANCELLED"


def test_workflow_contracts():
    with pytest.raises(ValueError):
        replace(definition(), steps=())
    with pytest.raises(ValueError):
        replace(definition(), steps=(definition().steps[0], definition().steps[0]))
    with pytest.raises(ValueError):
        replace(definition(), owner="")
    with pytest.raises(TypeError):
        replace(definition().steps[0], required="false")
