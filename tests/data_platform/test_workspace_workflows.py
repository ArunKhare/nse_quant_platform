"""Real disposable source/workspace DBs; recording audit ledger and child process double."""

from __future__ import annotations

import subprocess
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from pathlib import Path

import duckdb
import pytest
import yaml

from nse_quant.data_platform import workspace_workflows as module
from nse_quant.data_platform.workflow_cli import parse_args


class RecordingLedger:
    def __init__(self, conn):
        self.events = []
        self.plans = []

    def initialize(self):
        pass

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


@pytest.fixture
def options(tmp_path):
    repo = tmp_path / "repository"
    (repo / "scripts").mkdir(parents=True)
    (repo / "config").mkdir()
    (repo / "src").mkdir()
    for name in (
        "build_daily_rv.py",
        "manage_candles.py",
        "export_warehouse.py",
        "backtest_readiness.py",
        "run_walk_forward_backtest.py",
        "generate_backtest_report.py",
        "research_status_digest.py",
    ):
        (repo / "scripts" / name).write_text("# fixture script\n")
    for name in ("settings.yaml", "settings.test.yaml"):
        (repo / "config" / name).write_text("storage: {}\nsafety: {}\n")
    source = tmp_path / "original.duckdb"
    conn = duckdb.connect(str(source))
    conn.execute("CREATE TABLE option_stream (underlying VARCHAR, ts TIMESTAMPTZ, iv DOUBLE)")
    conn.execute("INSERT INTO option_stream VALUES ('NIFTY', '2026-10-30 06:00:00+00', .13)")
    conn.execute("CREATE TABLE market_regimes (symbol VARCHAR, ts TIMESTAMPTZ, regime VARCHAR)")
    conn.execute("INSERT INTO market_regimes VALUES ('NIFTY', '2026-10-30 06:00:00+00', 'NORMAL')")
    conn.execute(
        "CREATE TABLE spot_candles (symbol VARCHAR, ts TIMESTAMPTZ, interval VARCHAR, close DOUBLE)"
    )
    conn.execute("INSERT INTO spot_candles VALUES ('NIFTY', '2026-10-30 06:00:00+00', '1m', 25000)")
    conn.execute(
        "CREATE TABLE daily_rv_observations (symbol VARCHAR, trading_date DATE, rv DOUBLE)"
    )
    conn.execute("INSERT INTO daily_rv_observations VALUES ('NIFTY', '2026-10-30', .1)")
    conn.close()
    return module.WorkflowOptions(
        kind="eod",
        source_db=source,
        repository=repo,
        run_root=tmp_path / "runs",
        symbol="NIFTY",
        start_date=date(2026, 10, 30),
        end_date=date(2026, 10, 30),
        code_revision="test-commit",
        actor="qa",
        config=repo / "config/settings.yaml",
    )


def test_default_plan_does_not_write(options):
    before = module.file_hash(options.source_db)
    result = module.OfflineWorkflow(options).run()
    assert result["status"] == "PLANNED"
    assert not options.run_root.exists()
    assert module.file_hash(options.source_db) == before


def test_execution_requires_acknowledgement(options):
    with pytest.raises(ValueError, match="acknowledgement"):
        module.OfflineWorkflow(replace(options, execute=True))
    assert not options.run_root.exists()


def test_scope_validation(options):
    with pytest.raises(ValueError):
        module.OfflineWorkflow(replace(options, symbol="../NIFTY"))
    with pytest.raises(ValueError):
        module.OfflineWorkflow(replace(options, intervals="2m"))
    with pytest.raises(ValueError):
        module.OfflineWorkflow(replace(options, start_date=date(2026, 10, 29)))


def simulate_child(command, **kwargs):
    working = Path(kwargs["env"]["STORAGE__DB_PATH"])
    conn = duckdb.connect(str(working))
    conn.execute("UPDATE daily_rv_observations SET rv = .22")
    conn.close()
    return subprocess.CompletedProcess(command, 0)


def test_eod_isolates_mutations_and_exports(options, monkeypatch):
    monkeypatch.setattr(module, "AuditLedger", RecordingLedger)
    monkeypatch.setattr(module.subprocess, "run", simulate_child)
    original = module.file_hash(options.source_db)
    workflow = module.OfflineWorkflow(replace(options, execute=True, source_offline=True))
    report = workflow.run()
    assert report["status"] == "SUCCEEDED"
    assert module.file_hash(options.source_db) == original
    root = Path(str(report["run_directory"]))
    assert module.file_hash(root / "source_snapshot.duckdb") == original
    assert list((root / "checkpoints").glob("*.duckdb"))
    exports = list((root / "data/exports").glob("*.parquet"))
    assert len(exports) == 4
    conn = duckdb.connect()
    try:
        row = conn.execute(
            "SELECT rv FROM read_parquet(?)",
            [str(next(path for path in exports if path.name.startswith("daily_rv_")))],
        ).fetchone()
        assert row is not None and row[0] == 0.22
    finally:
        conn.close()
    assert workflow.ledger is not None
    for entry in workflow.ledger.plans[1:]:
        assert entry["parent_job_id"] == report["job_id"]
    settings = yaml.safe_load((root / "config/settings.yaml").read_text())
    assert settings["safety"]["trading_enabled"] is False
    assert settings["storage"]["db_path"] == str(root / "working.duckdb")


def test_failure_stops_before_exports_and_preserves_source(options, monkeypatch):
    monkeypatch.setattr(module, "AuditLedger", RecordingLedger)
    calls = []

    def failed(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 2)

    monkeypatch.setattr(module.subprocess, "run", failed)
    before = module.file_hash(options.source_db)
    workflow = module.OfflineWorkflow(replace(options, execute=True, source_offline=True))
    with pytest.raises(RuntimeError, match="exit code 2"):
        workflow.run()
    assert len(calls) == 1
    assert module.file_hash(options.source_db) == before
    assert workflow.root is not None and not (workflow.root / "data/exports").exists()
    assert workflow.ledger is not None and workflow.ledger.events[-1][1] == "FAILED"


def test_source_wal_fails_closed(options, monkeypatch):
    monkeypatch.setattr(module, "AuditLedger", RecordingLedger)
    Path(str(options.source_db) + ".wal").write_bytes(b"test")
    workflow = module.OfflineWorkflow(replace(options, execute=True, source_offline=True))
    with pytest.raises(RuntimeError, match="WAL"):
        workflow.run()
    assert workflow.root is not None and not (workflow.root / "working.duckdb").exists()


def test_cli_explicit_dates_and_safe_defaults(options):
    parsed = parse_args(
        "eod",
        [
            "--source-db",
            str(options.source_db),
            "--config",
            str(options.config),
            "--repository",
            str(options.repository),
            "--trade-date",
            "2026-10-30",
        ],
    )
    assert not parsed.execute and not parsed.source_offline
    assert parsed.end_date == date(2026, 10, 30)


def test_daily_binds_real_run_paths_and_warns_on_digest(options, monkeypatch):
    monkeypatch.setattr(module, "AuditLedger", RecordingLedger)
    seen = []

    def child(command, **kwargs):
        script = Path(command[1]).name
        seen.append((script, command))
        root = Path(kwargs["cwd"])

        def argument(name):
            return command[command.index(name) + 1]

        if script == "export_warehouse.py":
            directory = Path(argument("--export-dir"))
            directory.mkdir(parents=True, exist_ok=True)
            (directory / (command[2] + ".fixture")).write_text("fixture")
        elif script == "backtest_readiness.py":
            output = Path(argument("--output"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text('{"ready":true}')
        elif script == "run_walk_forward_backtest.py":
            Path(argument("--output-dir")).mkdir(parents=True)
            folder = Path(argument("--walk-forward-dir")) / argument("--run-id")
            folder.mkdir(parents=True)
            (folder / "fixture.json").write_text("{}")
            (Path(argument("--output-dir")) / "fixture.csv").write_text("fixture")
        elif script == "generate_backtest_report.py":
            folder = Path(argument("--output-dir")) / argument("--run-id")
            folder.mkdir(parents=True)
            (folder / "fixture.html").write_text("fixture")
        elif script == "research_status_digest.py":
            return subprocess.CompletedProcess(command, 2)
        assert Path(kwargs["env"]["STORAGE__DB_PATH"]) == root / "working.duckdb"
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", child)
    workflow = module.OfflineWorkflow(
        replace(
            options,
            kind="daily",
            execute=True,
            source_offline=True,
        )
    )
    report = workflow.run()
    assert report["status"] == "SUCCEEDED_WITH_WARNINGS"
    assert report["steps"][-1]["step_id"] == "digest"
    assert report["steps"][-1]["status"] == "FAILED"
    assert any(name == "run_walk_forward_backtest.py" for name, _ in seen)


def test_real_ledger_integration(options, monkeypatch):
    monkeypatch.setattr(module.subprocess, "run", simulate_child)
    workflow = module.OfflineWorkflow(replace(options, execute=True, source_offline=True))
    report = workflow.run()
    root = Path(str(report["run_directory"]))
    conn = duckdb.connect(str(root / "audit.duckdb"), read_only=True)
    try:
        rows = conn.execute(
            "SELECT job_id FROM medallion_audit.jobs WHERE parent_job_id = ?",
            [report["job_id"]],
        ).fetchall()
        assert len(rows) >= 6
        state = conn.execute(
            "SELECT state FROM medallion_audit.job_events WHERE job_id = ? "
            "ORDER BY event_index DESC LIMIT 1",
            [report["job_id"]],
        ).fetchone()
        assert state is not None and state[0] == "SUCCEEDED"
    finally:
        conn.close()
