"""Audited offline workflow adapters for unmigrated legacy datasets.

Original data is never a subprocess write target. Outputs remain run-local and
are not claimed to be Bronze/Silver/Gold. This is not a production promotion API.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import duckdb
import yaml

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.manifests import ManifestStore, digest


class ConnectionOwner(Protocol):
    conn: duckdb.DuckDBPyConnection


def build_export_path(
    *,
    export_dir: Path,
    underlying: str,
    trading_date: date,
    dataset: str,
) -> Path:
    return (
        export_dir
        / f"underlying={underlying}"
        / f"year={trading_date.year}"
        / f"month={trading_date.month:02d}"
        / f"{dataset}_{trading_date.isoformat()}.parquet"
    )


def get_option_stream_count_for_date(
    *,
    store: ConnectionOwner,
    underlying: str,
    trading_date: date,
) -> int:
    row = store.conn.execute(
        "SELECT count(*) FROM option_stream WHERE underlying = ? AND CAST(ts AS DATE) = ?",
        [underlying, trading_date],
    ).fetchone()
    return int(row[0]) if row is not None else 0


def file_hash(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def file_records(paths: tuple[Path, ...]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Required workflow input/output is missing: {path.name}")
        selected = sorted(path.rglob("*")) if path.is_dir() else [path]
        for item in selected:
            if item.is_file() and "__pycache__" not in item.parts:
                records.append(
                    {
                        "path": str(item.resolve()),
                        "bytes": item.stat().st_size,
                        "sha256": file_hash(item),
                    }
                )
    return records


def encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@dataclass(frozen=True)
class WorkflowOptions:
    kind: str
    source_db: Path
    repository: Path
    run_root: Path
    symbol: str
    start_date: date
    end_date: date
    code_revision: str
    actor: str
    config: Path
    execute: bool = False
    source_offline: bool = False
    skip_export: bool = False
    intervals: str = "5m,15m,30m,60m"
    train_days: int = 2
    test_days: int = 1
    min_train_trades: int = 10
    min_test_trades: int = 1
    workers: int = 1
    iv_collapse_pct: tuple[float, ...] = (20.0,)
    expected_move_buffer: tuple[float, ...] = (1.25,)
    entry_cooldown_minutes: tuple[int, ...] = (15,)

    def validate(self) -> None:
        if self.kind not in {"daily", "eod"}:
            raise ValueError("Unsupported workflow")
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", self.symbol) is None:
            raise ValueError("Use a trimmed uppercase symbol")
        if self.start_date > self.end_date:
            raise ValueError("Start date must not exceed end date")
        if self.kind == "eod" and self.start_date != self.end_date:
            raise ValueError("EOD scope must be one explicit trading date")
        if not self.source_db.is_file() or not self.config.is_file():
            raise ValueError("Source database and config must exist")
        if self.execute and (not self.source_offline or not self.code_revision.strip()):
            raise ValueError("Execution requires source-offline acknowledgement and code revision")
        if any(
            value < 1
            for value in (
                self.train_days,
                self.test_days,
                self.min_train_trades,
                self.min_test_trades,
                self.workers,
            )
        ):
            raise ValueError("Training, trade and worker counts must be positive")
        if self.run_root.resolve() in self.source_db.resolve().parents:
            raise ValueError("Run root must not contain the source database")
        if not self.actor.strip():
            raise ValueError("Actor identity is required")
        for folder in ("src", "scripts"):
            code = (self.repository / folder).resolve()
            if not code.is_dir():
                raise ValueError("Repository src and scripts directories must exist")
            if self.run_root.resolve() == code or code in self.run_root.resolve().parents:
                raise ValueError("Run root must be outside source-code directories")
        if (
            not self.iv_collapse_pct
            or not self.expected_move_buffer
            or not self.entry_cooldown_minutes
        ):
            raise ValueError("Parameter grids must not be empty")
        if any(
            not math.isfinite(value)
            for value in (
                *self.iv_collapse_pct,
                *self.expected_move_buffer,
            )
        ):
            raise ValueError("Parameter grids must contain finite values")
        requested = [item.strip() for item in self.intervals.split(",") if item.strip()]
        if any(item not in {"5m", "15m", "30m", "60m"} for item in requested):
            raise ValueError("Unsupported candle interval")


class OfflineWorkflow:
    def __init__(self, options: WorkflowOptions) -> None:
        options.validate()
        self.options = options
        self.root: Path | None = None
        self.ledger: AuditLedger | None = None
        self.manifests: ManifestStore | None = None
        self.parent: str | None = None
        self.outcomes: list[dict[str, object]] = []
        self.environment: dict[str, str] = {}
        self._steps: set[str] = set()
        self.config_hash = ""
        self.snapshot_ref: str | None = None
        self.code_root = options.repository

    def plan(self) -> dict[str, object]:
        value = asdict(self.options)
        for key in ("source_db", "repository", "run_root", "config"):
            value[key] = str(value[key])
        for key in ("start_date", "end_date"):
            value[key] = value[key].isoformat()
        value["execution_model"] = "offline_legacy_workspace"
        value["source_write_allowed"] = False
        value["steps"] = (
            [
                "snapshot",
                "code_snapshot",
                "configure",
                "export_options",
                "export_regimes",
                "readiness",
                "walk_forward",
                "report",
                "digest",
            ]
            if self.options.kind == "daily"
            else [
                "snapshot",
                "code_snapshot",
                "configure",
                "daily_rv",
                "daily_candles",
                "intraday_candles",
                "exports",
                "summary",
            ]
        )
        return value

    def _require_context(self) -> tuple[Path, AuditLedger, ManifestStore, str]:
        if (
            self.root is None
            or self.ledger is None
            or self.manifests is None
            or self.parent is None
        ):
            raise RuntimeError("Workflow execution context is not initialized")
        return self.root, self.ledger, self.manifests, self.parent

    def step(
        self,
        name: str,
        action: Callable[[], tuple[Path, ...]],
        inputs: tuple[Path, ...],
        *,
        required: bool = True,
    ) -> tuple[Path, ...]:
        root, ledger, manifests, parent = self._require_context()
        if name in self._steps:
            raise ValueError("Duplicate workflow step identity")
        self._steps.add(name)
        preserved_inputs = self.preserve_working_database(inputs, name + "_input")
        payload = encode(
            {
                "kind": "legacy_workspace_step",
                "step_id": name,
                "source_snapshot_ref": getattr(self, "snapshot_ref", None),
                "inputs": file_records(preserved_inputs),
                "mutation_scope": (
                    "all_available_dates_in_isolated_workspace"
                    if name == "daily_rv"
                    else "requested_scope_or_artifacts"
                ),
                "scope": {
                    "symbol": self.options.symbol,
                    "start_inclusive": self.options.start_date.isoformat(),
                    "end_inclusive": self.options.end_date.isoformat(),
                },
            }
        )
        manifests.put(payload)
        job = ledger.plan_job(
            command_name=f"workflow.{self.options.kind}.step.{name}@1",
            actor_id=self.options.actor,
            scope_ref="sha256:" + digest(payload),
            code_revision=self.options.code_revision,
            config_hash=self.config_hash,
            parent_job_id=parent,
        )
        outcome: dict[str, object] = {"step_id": name, "job_id": job, "required": required}
        self.outcomes.append(outcome)
        try:
            with ledger.execution(job):
                outputs = action()
                output_records = file_records(
                    self.preserve_working_database(outputs, name + "_output")
                )
                if outputs and not output_records:
                    raise ValueError("Step returned no verifiable output files")
                receipt = encode(
                    {
                        "kind": "step_receipt",
                        "job_id": job,
                        "step_id": name,
                        "input_plan": digest(payload),
                        "outputs": output_records,
                    }
                )
                manifests.put(receipt)
                outcome.update(status="SUCCEEDED", receipt_id=digest(receipt))
                return outputs
        except Exception:
            outcome.update(status="FAILED", reason_code="STEP_EXECUTION_FAILED")
            if required:
                raise
            return ()

    def preserve_working_database(
        self,
        paths: tuple[Path, ...],
        label: str,
    ) -> tuple[Path, ...]:
        root, _, _, _ = self._require_context()
        preserved = []
        for path in paths:
            if path.resolve() != (root / "working.duckdb").resolve():
                preserved.append(path)
                continue
            if Path(str(path) + ".wal").exists():
                raise RuntimeError("Workspace writer left a WAL; checkpoint before publication")
            directory = root / "checkpoints"
            directory.mkdir(exist_ok=True)
            destination = directory / (label + ".duckdb")
            with path.open("rb") as reader, destination.open("xb") as writer:
                shutil.copyfileobj(reader, writer)
                writer.flush()
                os.fsync(writer.fileno())
            if file_hash(destination) != file_hash(path):
                raise RuntimeError("Workspace checkpoint checksum mismatch")
            preserved.append(destination)
        return tuple(preserved)

    def snapshot(self) -> tuple[Path, ...]:
        root, _, manifests, _ = self._require_context()
        source = self.options.source_db.resolve()
        if Path(str(source) + ".wal").exists():
            raise RuntimeError("Source WAL exists; close/checkpoint the writer before snapshot")
        target = root / "source_snapshot.duckdb"
        conn = duckdb.connect(str(source), read_only=True)
        try:
            before = file_hash(source)
            with source.open("rb") as reader, target.open("xb") as writer:
                shutil.copyfileobj(reader, writer)
                writer.flush()
                os.fsync(writer.fileno())
            if file_hash(source) != before or file_hash(target) != before:
                raise RuntimeError("Source changed or copied snapshot failed checksum validation")
        finally:
            conn.close()
        check = duckdb.connect(str(target), read_only=True)
        try:
            tables = check.execute("SHOW TABLES").fetchall()
            if not tables:
                raise ValueError("Source snapshot has no tables")
        finally:
            check.close()
        payload = encode(
            {
                "kind": "legacy_database_snapshot",
                "sha256": before,
                "file": str(target),
                "original_path": str(source),
            }
        )
        manifests.put(payload)
        self.snapshot_ref = "sha256:" + digest(payload)
        shutil.copyfile(target, root / "working.duckdb")
        return (target,)

    def freeze_code(self) -> tuple[Path, ...]:
        root, _, _, _ = self._require_context()
        destination = root / "code"
        for folder in ("src", "scripts"):
            source = self.options.repository / folder
            target = destination / folder
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            source_records = {
                str(Path(str(item["path"])).relative_to(source.resolve())): item["sha256"]
                for item in file_records((source,))
                if not str(item["path"]).endswith(".pyc")
            }
            copied_records = {
                str(Path(str(item["path"])).relative_to(target.resolve())): item["sha256"]
                for item in file_records((target,))
                if not str(item["path"]).endswith(".pyc")
            }
            if source_records != copied_records:
                raise RuntimeError("Code changed while freezing the workflow input")
        self.code_root = destination
        return (destination,)

    def configure(self) -> tuple[Path, ...]:
        root, _, _, _ = self._require_context()
        config_dir = root / "config"
        config_dir.mkdir()
        outputs = []
        for filename in ("settings.yaml", "settings.test.yaml"):
            source = (
                self.options.config
                if filename == "settings.yaml"
                else (self.options.repository / "config" / filename)
            )
            if not source.is_file():
                raise FileNotFoundError("Required repository test configuration is missing")
            settings = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
            settings.pop("secrets", None)
            settings.setdefault("storage", {})["db_path"] = str(root / "working.duckdb")
            settings["storage"]["parquet_dir"] = str(root / "data/exports")
            settings.setdefault("safety", {}).update(
                trading_enabled=False,
                paper_trading=True,
                dry_run=True,
            )
            settings.setdefault("notifier", {})["enabled"] = False
            destination = config_dir / filename
            destination.write_text(yaml.safe_dump(settings), encoding="utf-8")
            outputs.append(destination)
        self.environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("SECRETS__", "KITE_", "TELEGRAM_"))
        }
        self.environment.update(
            {
                "STORAGE__DB_PATH": str(root / "working.duckdb"),
                "STORAGE__PARQUET_DIR": str(root / "data/exports"),
                "SAFETY__TRADING_ENABLED": "false",
                "SAFETY__PAPER_TRADING": "true",
                "SAFETY__DRY_RUN": "true",
                "NOTIFIER__ENABLED": "false",
                "NSE_QUANT_SETTINGS": str(config_dir / "settings.yaml"),
                "PYTHONPATH": str(self.code_root / "src")
                + os.pathsep
                + self.environment.get("PYTHONPATH", ""),
            }
        )
        return tuple(outputs)

    def command(
        self,
        name: str,
        script: str,
        arguments: list[str],
        outputs: tuple[Path, ...],
        inputs: tuple[Path, ...],
        *,
        required: bool = True,
    ) -> tuple[Path, ...]:
        root, _, _, _ = self._require_context()
        source = self.code_root / "scripts" / script

        def action() -> tuple[Path, ...]:
            before = file_hash(source)
            log_dir = root / "logs"
            log_dir.mkdir(exist_ok=True)
            with (log_dir / f"{name}.log").open("xb") as log:
                completed = subprocess.run(
                    [sys.executable, str(source), *arguments],
                    cwd=root,
                    env=self.environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            if completed.returncode != 0:
                raise RuntimeError(f"Step {name} failed with exit code {completed.returncode}")
            if file_hash(source) != before:
                raise RuntimeError("Invoked script changed during execution")
            return outputs

        arguments_dir = root / "command_plans"
        arguments_dir.mkdir(exist_ok=True)
        argument_manifest = arguments_dir / (name + ".json")
        with argument_manifest.open("xb") as handle:
            handle.write(
                encode(
                    {"script": str(source), "arguments": arguments, "working_directory": str(root)}
                )
            )
        return self.step(name, action, (source, argument_manifest, *inputs), required=required)

    def query_dates(self) -> list[str]:
        root, _, _, _ = self._require_context()
        conn = duckdb.connect(str(root / "working.duckdb"), read_only=True)
        try:
            return [
                str(row[0])
                for row in conn.execute(
                    """SELECT DISTINCT CAST(ts AS DATE) FROM option_stream
                WHERE underlying = ? AND CAST(ts AS DATE) BETWEEN ? AND ? ORDER BY 1""",
                    [self.options.symbol, self.options.start_date, self.options.end_date],
                ).fetchall()
            ]
        finally:
            conn.close()

    def daily(self) -> None:
        root, _, _, _ = self._require_context()
        warehouse = root / "data/exports"
        dates = self.query_dates()
        if not dates:
            raise ValueError("No option observations in the selected research range")
        source = root / "source_snapshot.duckdb"
        for index, day in enumerate(dates):
            self.command(
                f"export_options_{index}",
                "export_warehouse.py",
                [
                    "option-stream",
                    "--symbol",
                    self.options.symbol,
                    "--date",
                    day,
                    "--export-dir",
                    str(warehouse),
                ],
                (warehouse,),
                (source,),
            )
        self.command(
            "export_regimes",
            "export_warehouse.py",
            [
                "market-regimes",
                "--symbol",
                self.options.symbol,
                "--start-date",
                self.options.start_date.isoformat(),
                "--end-date",
                self.options.end_date.isoformat(),
                "--export-dir",
                str(warehouse),
            ],
            (warehouse,),
            (source,),
        )
        partition = warehouse / f"underlying={self.options.symbol}/year=*/month=*"
        readiness = root / "data/research/backtest_readiness.json"
        self.command(
            "readiness",
            "backtest_readiness.py",
            [
                "--underlying",
                self.options.symbol,
                "--warehouse-glob",
                str(partition / "option_stream_*.parquet"),
                "--regime-glob",
                str(partition / "market_regime_*.parquet"),
                "--output",
                str(readiness),
            ],
            (readiness,),
            (warehouse, root / "working.duckdb"),
        )
        backtests = root / "data/research/backtests"
        folds = root / "data/research/walk_forward"
        run_id = root.name
        arguments = [
            "--warehouse-dir",
            str(warehouse),
            "--output-dir",
            str(backtests),
            "--walk-forward-dir",
            str(folds),
            "--symbol",
            self.options.symbol,
            "--start-date",
            self.options.start_date.isoformat(),
            "--end-date",
            self.options.end_date.isoformat(),
            "--run-id",
            run_id,
            "--train-days",
            str(self.options.train_days),
            "--test-days",
            str(self.options.test_days),
            "--min-train-trades",
            str(self.options.min_train_trades),
            "--min-test-trades",
            str(self.options.min_test_trades),
            "--workers",
            str(self.options.workers),
            "--iv-collapse-pct",
            *map(str, self.options.iv_collapse_pct),
            "--expected-move-buffer",
            *map(str, self.options.expected_move_buffer),
            "--entry-cooldown-minutes",
            *map(str, self.options.entry_cooldown_minutes),
        ]
        self.command(
            "walk_forward",
            "run_walk_forward_backtest.py",
            arguments,
            (backtests, folds / run_id),
            (warehouse, readiness),
        )
        reports = root / "data/research/reports"
        self.command(
            "report",
            "generate_backtest_report.py",
            [
                "--run-id",
                run_id,
                "--backtest-dir",
                str(backtests),
                "--output-dir",
                str(reports),
            ],
            (reports / run_id,),
            (backtests, folds / run_id),
        )
        self.command(
            "digest",
            "research_status_digest.py",
            [
                "--readiness",
                str(readiness),
                "--warehouse-dir",
                str(warehouse),
                "--registry",
                str(root / "data/research/experiments/experiment_index.csv"),
                "--output",
                str(root / "data/research/daily_status/daily_status.json"),
            ],
            (root / "data/research/daily_status/daily_status.json",),
            (readiness, reports),
            required=False,
        )

    def eod_exports(self) -> tuple[Path, ...]:
        root, _, _, _ = self._require_context()
        conn = duckdb.connect(str(root / "working.duckdb"), read_only=True)
        output_dir = root / "data/exports"
        output_dir.mkdir(parents=True)
        outputs = []
        metadata = []
        queries = {
            "option_stream": (
                "SELECT * FROM option_stream WHERE underlying = ? "
                "AND CAST(ts AS DATE) = ? ORDER BY ts"
            ),
            "market_regime": (
                "SELECT * FROM market_regimes WHERE symbol = ? "
                "AND CAST(ts AS DATE) = ? "
                "QUALIFY row_number() OVER "
                "(PARTITION BY symbol ORDER BY ts DESC) = 1"
            ),
            "spot_candles": (
                "SELECT * FROM spot_candles WHERE symbol = ? "
                "AND CAST(ts AS DATE) = ? ORDER BY interval, ts"
            ),
            "daily_rv": (
                "SELECT * FROM daily_rv_observations WHERE symbol = ? AND trading_date = ?"
            ),
        }
        try:
            for dataset, query in queries.items():
                filename = f"{dataset}_{self.options.symbol}_{self.options.end_date}.parquet"
                path = output_dir / filename
                if path.exists():
                    raise FileExistsError("Run output already exists")
                escaped = str(path).replace("'", "''")
                conn.execute(
                    f"COPY ({query}) TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)",
                    [self.options.symbol, self.options.end_date],
                )
                count = conn.execute(
                    "SELECT count(*) FROM read_parquet(?)",
                    [str(path)],
                ).fetchone()
                if count is None:
                    raise RuntimeError("Export row count validation failed")
                schema = conn.execute(
                    "DESCRIBE SELECT * FROM read_parquet(?)",
                    [str(path)],
                ).fetchall()
                metadata.append(
                    {
                        "dataset": dataset,
                        "rows": count[0],
                        "schema": schema,
                        "sha256": file_hash(path),
                        "path": str(path),
                        "status": "EMPTY" if count[0] == 0 else "EXPORTED",
                    }
                )
                outputs.append(path)
        finally:
            conn.close()
        export_manifest = output_dir / "export_manifest.json"
        export_manifest.write_bytes(encode({"datasets": metadata, "grade": "UNASSESSED_LEGACY"}))
        outputs.append(export_manifest)
        return tuple(outputs)

    def eod(self) -> None:
        root, _, _, _ = self._require_context()
        day = self.options.end_date.isoformat()
        database = root / "working.duckdb"
        self.command(
            "daily_rv",
            "build_daily_rv.py",
            ["--symbol", self.options.symbol],
            (database,),
            (database,),
        )
        self.command(
            "daily_candles",
            "manage_candles.py",
            [
                "aggregate-daily",
                "--symbol",
                self.options.symbol,
                "--start-date",
                day,
                "--end-date",
                day,
            ],
            (database,),
            (database,),
        )
        if self.options.intervals.strip():
            self.command(
                "intraday_candles",
                "manage_candles.py",
                [
                    "aggregate-intraday",
                    "--symbol",
                    self.options.symbol,
                    "--trade-date",
                    day,
                    "--intervals",
                    self.options.intervals,
                ],
                (database,),
                (database,),
            )
        if not self.options.skip_export:
            self.step("exports", self.eod_exports, (database,))

        def summary() -> tuple[Path, ...]:
            path = root / "summary.json"
            path.write_bytes(
                encode(
                    {
                        "kind": "eod_workspace_summary",
                        "symbol": self.options.symbol,
                        "trading_date": day,
                        "source_unchanged": (
                            file_hash(self.options.source_db)
                            == file_hash(root / "source_snapshot.duckdb")
                        ),
                    }
                )
            )
            return (path,)

        self.step("summary", summary, (database,))

    def run(self) -> dict[str, object]:
        plan = self.plan()
        if not self.options.execute:
            return {"status": "PLANNED", "plan": plan}
        root = self.options.run_root.resolve() / (
            f"{self.options.kind}_{self.options.symbol}_{self.options.end_date}_{uuid4().hex}"
        )
        root.mkdir(parents=True, exist_ok=False)
        self.root = root
        self.config_hash = file_hash(self.options.config)
        conn = duckdb.connect(str(root / "audit.duckdb"))
        try:
            self.ledger = AuditLedger(conn)
            self.ledger.initialize()
            self.manifests = ManifestStore(root / "manifests")
            payload = encode(plan)
            self.manifests.put(payload)
            self.parent = self.ledger.plan_job(
                command_name=f"workflow.{self.options.kind}@2",
                actor_id=self.options.actor,
                scope_ref="sha256:" + digest(payload),
                code_revision=self.options.code_revision,
                config_hash=self.config_hash,
            )
            try:
                with self.ledger.execution(self.parent):
                    self.step("snapshot", self.snapshot, (self.options.source_db,))
                    self.step(
                        "code_snapshot",
                        self.freeze_code,
                        (
                            self.options.repository / "src",
                            self.options.repository / "scripts",
                        ),
                    )
                    self.step(
                        "configure",
                        self.configure,
                        (
                            self.options.config,
                            self.options.repository / "config/settings.test.yaml",
                        ),
                    )
                    if self.options.kind == "daily":
                        self.daily()
                    else:
                        self.eod()
                    source_hash = file_hash(self.options.source_db)
                    if source_hash != file_hash(root / "source_snapshot.duckdb"):
                        raise RuntimeError("Original source checksum changed during workflow")
                    status = (
                        "SUCCEEDED_WITH_WARNINGS"
                        if any(item["status"] == "FAILED" for item in self.outcomes)
                        else "SUCCEEDED"
                    )
                    report = {
                        "status": status,
                        "job_id": self.parent,
                        "run_directory": str(root),
                        "steps": self.outcomes,
                    }
                    self.manifests.put(encode(report))
                    (root / "workflow_result.json").write_bytes(encode(report))
                    return report
            except BaseException:
                failure = {
                    "status": "FAILED",
                    "job_id": self.parent,
                    "run_directory": str(root),
                    "steps": self.outcomes,
                }
                with suppress(Exception):
                    self.manifests.put(encode(failure))
                raise
            finally:
                conn.close()
        finally:
            conn.close()
