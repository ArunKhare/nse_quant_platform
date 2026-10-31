"""Audited command execution through the A1 ledger interface.

Callbacks are trusted services, not sandboxed code. No legacy command is auto-bound.
"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from typing import Protocol

from nse_quant.data_platform.commands import Category, CommandRegistry, CommandResult
from nse_quant.data_platform.manifests import ManifestStore, digest
from nse_quant.data_platform.scopes import ExecutionScope


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


@dataclass(frozen=True)
class RunReport:
    plan_id: str
    job_id: str | None
    result_id: str | None
    result: CommandResult | None
    plan_json: str


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class CommandRunner:
    def __init__(
        self,
        registry: CommandRegistry,
        manifests: ManifestStore,
        ledger: Ledger,
    ) -> None:
        self.registry = registry
        self.manifests = manifests
        self.ledger = ledger

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
    ) -> RunReport:
        definition, executor = self.registry.resolve(name, version)
        if any(not item.strip() for item in (actor_id, code_revision, config_hash)):
            raise ValueError("Actor, code revision and config hash are required")
        if (
            definition.category in {Category.NORMALIZE, Category.BUILD, Category.EXPORT}
            and not scope.input_snapshot_refs
        ):
            raise ValueError("This operation requires pinned input snapshot references")
        plan = {
            "manifest_version": 1,
            "command": asdict(definition),
            "scope": scope.as_dict(),
            "actor_id": actor_id,
            "code_revision": code_revision,
            "config_hash": config_hash,
            "parent_job_id": parent_job_id,
        }
        payload = _json(plan)
        plan_id = digest(payload)
        if dry_run:
            return RunReport(plan_id, None, None, None, payload.decode("utf-8"))

        self.manifests.put(payload)
        job_id = self.ledger.plan_job(
            command_name=definition.name + "@" + definition.version,
            actor_id=actor_id,
            scope_ref="sha256:" + plan_id,
            code_revision=code_revision,
            config_hash=config_hash,
            parent_job_id=parent_job_id,
        )
        with self.ledger.execution(job_id):
            result = executor(scope)
            if not isinstance(result, CommandResult):
                raise TypeError("Executor must return CommandResult, not a subprocess exit code")
            if (
                definition.category in {Category.EXPORT, Category.INSPECT, Category.WORKFLOW}
                and result.rows_written
            ):
                raise ValueError("This category must not report direct domain-row writes")
            if (
                definition.category in {Category.BUILD, Category.EXPORT, Category.NORMALIZE}
                and not result.output_refs
            ):
                raise ValueError("Operation must identify its output or empty-result manifest")
            receipt = _json(
                {
                    "manifest_version": 1,
                    "job_id": job_id,
                    "plan_id": plan_id,
                    "result": asdict(result),
                }
            )
            self.manifests.put(receipt)
            result_id = digest(receipt)
        return RunReport(plan_id, job_id, result_id, result, payload.decode("utf-8"))
