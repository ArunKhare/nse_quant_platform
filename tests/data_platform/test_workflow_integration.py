"""Local integration against the QA-passed A1 ledger and A2a command runner."""

from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.commands import (
    Category,
    CommandDefinition,
    CommandRegistry,
    CommandResult,
)
from nse_quant.data_platform.manifests import ManifestStore
from nse_quant.data_platform.runner import CommandRunner
from nse_quant.data_platform.scopes import ExecutionScope
from nse_quant.data_platform.workflows import (
    WorkflowDefinition,
    WorkflowFailed,
    WorkflowRunner,
    WorkflowStep,
)


@pytest.mark.parametrize("failure", [None, "required", "optional"])
def test_real_parent_child_execution(tmp_path, failure):
    conn = duckdb.connect(":memory:")
    try:
        ledger = AuditLedger(conn)
        ledger.initialize()
        registry = CommandRegistry()
        executed = []

        def required(scope):
            executed.append("required")
            if failure == "required":
                raise ValueError("required operation rejected")
            return CommandResult(rows_read=1)

        def optional(scope):
            executed.append("optional")
            if failure == "optional":
                raise ValueError("optional operation rejected")
            return CommandResult(rows_read=1)

        registry.register(
            CommandDefinition(
                "inspect.required",
                "1",
                Category.INSPECT,
                "qa",
                reads=("silver.option_quotes",),
            ),
            required,
        )
        registry.register(
            CommandDefinition(
                "inspect.optional",
                "1",
                Category.INSPECT,
                "qa",
                reads=("silver.option_quotes",),
            ),
            optional,
        )
        scope = ExecutionScope(
            symbols=("NIFTY",),
            start=datetime(2026, 10, 30, tzinfo=UTC),
            end=datetime(2026, 10, 31, tzinfo=UTC),
        )
        manifests = ManifestStore(tmp_path / "manifests")
        children = CommandRunner(registry, manifests, ledger)
        runner = WorkflowRunner(children, ledger, manifests)
        definition = WorkflowDefinition(
            "workflow.qa",
            "1",
            "qa",
            (
                WorkflowStep("required", "inspect.required", "1", scope),
                WorkflowStep("optional", "inspect.optional", "1", scope, required=False),
            ),
        )

        def execute():
            return runner.run(
                definition,
                actor_id="qa",
                code_revision="test-commit",
                config_hash="test-config",
                dry_run=False,
            )

        if failure == "required":
            with pytest.raises(WorkflowFailed) as error:
                execute()
            report = error.value.report
            assert executed == ["required"]
        else:
            report = execute()
            assert executed == ["required", "optional"]
            expected = "SUCCEEDED_WITH_WARNINGS" if failure else "SUCCEEDED"
            assert report.status == expected
        assert report.job_id is not None and report.receipt_id is not None
        manifests.read(report.receipt_id)
        children_rows = conn.execute(
            "SELECT job_id FROM medallion_audit.jobs WHERE parent_job_id = ?",
            [report.job_id],
        ).fetchall()
        assert len(children_rows) == (1 if failure == "required" else 2)
        parent_state = conn.execute(
            """
            SELECT state FROM medallion_audit.job_events
            WHERE job_id = ? ORDER BY event_index DESC LIMIT 1
            """,
            [report.job_id],
        ).fetchone()
        assert parent_state is not None
        assert parent_state[0] == ("FAILED" if failure == "required" else "SUCCEEDED")
    finally:
        conn.close()
