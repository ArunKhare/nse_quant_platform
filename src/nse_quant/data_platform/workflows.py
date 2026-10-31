"""Audited sequential workflows over the A2a registered-command runner.

No legacy script is auto-bound. Workflow orchestration cannot roll back child effects.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from nse_quant.data_platform.scopes import ExecutionScope


class ChildReport(Protocol):
    @property
    def plan_id(self) -> str: ...

    @property
    def job_id(self) -> str | None: ...

    @property
    def result_id(self) -> str | None: ...

    @property
    def plan_json(self) -> str: ...


class ChildRunner(Protocol):
    def run(
        self,
        *,
        name: str,
        version: str,
        scope: ExecutionScope,
        actor_id: str,
        code_revision: str,
        config_hash: str,
        dry_run: bool = True,
        parent_job_id: str | None = None,
    ) -> ChildReport: ...


class Ledger(Protocol):
    def plan_job(
        self,
        *,
        command_name: str,
        actor_id: str,
        scope_ref: str,
        code_revision: str,
        config_hash: str,
        parent_job_id: str | None = None,
    ) -> str: ...

    def execution(self, job_id: str) -> AbstractContextManager[str]: ...


class Manifests(Protocol):
    def put(self, payload: bytes) -> object: ...


def _encode(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _identity(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    command_name: str
    command_version: str
    scope: ExecutionScope
    required: bool = True

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.step_id,
                self.command_name,
                self.command_version,
            )
        ):
            raise ValueError("Step and command identities are required")
        if type(self.required) is not bool:
            raise TypeError("required must be a bool")


@dataclass(frozen=True)
class WorkflowDefinition:
    name: str
    version: str
    owner: str
    steps: tuple[WorkflowStep, ...]

    def __post_init__(self) -> None:
        if any(not value.strip() for value in (self.name, self.version, self.owner)):
            raise ValueError("Workflow identity and owner are required")
        if not isinstance(self.steps, tuple):
            raise TypeError("Steps must be an immutable tuple")
        if not self.steps or any(not isinstance(step, WorkflowStep) for step in self.steps):
            raise ValueError("Workflow needs valid steps")
        if len({step.step_id for step in self.steps}) != len(self.steps):
            raise ValueError("Step identities must be unique")


@dataclass(frozen=True)
class StepOutcome:
    step_id: str
    required: bool
    status: str
    child_job_id: str | None = None
    child_result_id: str | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class WorkflowReport:
    plan_id: str
    job_id: str | None
    receipt_id: str | None
    status: str
    outcomes: tuple[StepOutcome, ...]
    plan_json: str


class WorkflowFailed(RuntimeError):
    def __init__(self, report: WorkflowReport) -> None:
        self.report = report
        super().__init__("Required workflow step failed; inspect audited child execution")


class WorkflowRunner:
    def __init__(self, children: ChildRunner, ledger: Ledger, manifests: Manifests) -> None:
        self.children = children
        self.ledger = ledger
        self.manifests = manifests

    def run(
        self,
        definition: WorkflowDefinition,
        *,
        actor_id: str,
        code_revision: str,
        config_hash: str,
        dry_run: bool = True,
        parent_job_id: str | None = None,
    ) -> WorkflowReport:
        if any(not value.strip() for value in (actor_id, code_revision, config_hash)):
            raise ValueError("Execution identifiers are required")
        planned_children = []
        for step in definition.steps:
            report = self.children.run(
                name=step.command_name,
                version=step.command_version,
                scope=step.scope,
                actor_id=actor_id,
                code_revision=code_revision,
                config_hash=config_hash,
                dry_run=True,
            )
            planned_children.append(
                {
                    "step_id": step.step_id,
                    "required": step.required,
                    "preflight_plan_id": report.plan_id,
                    "preflight_plan": json.loads(report.plan_json),
                }
            )
        payload = _encode(
            {
                "manifest_version": 1,
                "kind": "workflow_plan",
                "name": definition.name,
                "version": definition.version,
                "owner": definition.owner,
                "actor_id": actor_id,
                "code_revision": code_revision,
                "config_hash": config_hash,
                "parent_job_id": parent_job_id,
                "steps": planned_children,
            }
        )
        plan_id = _identity(payload)
        plan_json = payload.decode()
        if dry_run:
            return WorkflowReport(plan_id, None, None, "PLANNED", (), plan_json)
        self.manifests.put(payload)
        job_id = self.ledger.plan_job(
            command_name=definition.name + "@" + definition.version,
            actor_id=actor_id,
            scope_ref="sha256:" + plan_id,
            code_revision=code_revision,
            config_hash=config_hash,
            parent_job_id=parent_job_id,
        )
        outcomes: list[StepOutcome] = []
        with self.ledger.execution(job_id):
            for index, step in enumerate(definition.steps):
                try:
                    child = self.children.run(
                        name=step.command_name,
                        version=step.command_version,
                        scope=step.scope,
                        actor_id=actor_id,
                        code_revision=code_revision,
                        config_hash=config_hash,
                        dry_run=False,
                        parent_job_id=job_id,
                    )
                    if child.job_id is None or child.result_id is None:
                        raise ValueError("Child execution did not return an audited receipt")
                    outcomes.append(
                        StepOutcome(
                            step.step_id,
                            step.required,
                            "SUCCEEDED",
                            child.job_id,
                            child.result_id,
                        )
                    )
                except Exception as error:
                    outcomes.append(
                        StepOutcome(
                            step.step_id,
                            step.required,
                            "FAILED",
                            reason_code="CHILD_EXECUTION_FAILED",
                        )
                    )
                    if step.required:
                        outcomes.extend(
                            StepOutcome(
                                pending.step_id,
                                pending.required,
                                "NOT_RUN",
                                reason_code="REQUIRED_STEP_FAILED",
                            )
                            for pending in definition.steps[index + 1 :]
                        )
                        receipt_id = None
                        try:
                            receipt_id = self._receipt(job_id, plan_id, "FAILED", outcomes)
                        except Exception as receipt_error:
                            error.add_note(
                                f"Workflow receipt failure: {type(receipt_error).__name__}"
                            )
                        failure = WorkflowFailed(
                            WorkflowReport(
                                plan_id,
                                job_id,
                                receipt_id,
                                "FAILED",
                                tuple(outcomes),
                                plan_json,
                            )
                        )
                        raise failure from error
            status = (
                "SUCCEEDED_WITH_WARNINGS"
                if any(item.status == "FAILED" for item in outcomes)
                else "SUCCEEDED"
            )
            receipt_id = self._receipt(job_id, plan_id, status, outcomes)
        return WorkflowReport(plan_id, job_id, receipt_id, status, tuple(outcomes), plan_json)

    def _receipt(
        self,
        job_id: str,
        plan_id: str,
        status: str,
        outcomes: list[StepOutcome],
    ) -> str:
        payload = _encode(
            {
                "manifest_version": 1,
                "kind": "workflow_receipt",
                "job_id": job_id,
                "plan_id": plan_id,
                "status": status,
                "steps": [asdict(item) for item in outcomes],
            }
        )
        self.manifests.put(payload)
        return _identity(payload)
