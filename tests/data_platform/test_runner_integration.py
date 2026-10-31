"""Run locally against the QA-passed A1 AuditLedger (not supplied again in A2)."""

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


@pytest.mark.parametrize("fail", [False, True])
def test_runner_with_real_foundation_ledger(tmp_path, fail):
    conn = duckdb.connect(":memory:")
    try:
        ledger = AuditLedger(conn)
        ledger.initialize()
        registry = CommandRegistry()

        def operation(scope):
            if fail:
                raise ValueError("operation rejected")
            return CommandResult(rows_read=1)

        registry.register(
            CommandDefinition(
                name="inspect.test",
                version="1",
                category=Category.INSPECT,
                owner="qa",
                reads=("silver.option_quotes",),
            ),
            operation,
        )
        runner = CommandRunner(registry, ManifestStore(tmp_path / "manifests"), ledger)
        scope = ExecutionScope(
            symbols=("NIFTY",),
            start=datetime(2026, 10, 30, tzinfo=UTC),
            end=datetime(2026, 10, 31, tzinfo=UTC),
        )

        def run_operation():
            return runner.run(
                name="inspect.test",
                version="1",
                scope=scope,
                actor_id="qa",
                code_revision="test-commit",
                config_hash="test-config",
                dry_run=False,
            )

        if fail:
            with pytest.raises(ValueError, match="operation rejected"):
                run_operation()
        else:
            report = run_operation()
            assert report.job_id is not None and report.result_id is not None
        events = conn.execute(
            "SELECT state FROM medallion_audit.job_events ORDER BY event_index"
        ).fetchall()
        assert events == [("PLANNED",), ("RUNNING",), ("FAILED" if fail else "SUCCEEDED",)]
    finally:
        conn.close()
