# Multi-terminal storage reconciliation and bounded validation

Baseline: 23bf4c6cf8cf7c30754b0e2413f20755435b6767, feat/medallion-feature-store.
Status: candidate implementation/clarification; operational cutover NOT complete.

## Verified runtime findings at this baseline

- persistence/store_factory.py provides separate market_data, decisions and
  paper_orders open helpers. It forwards to DuckDBStore; it neither verifies
  caller role nor solves active native-file writer/read-process locking.
- persistence/store_paths.py resolves these under operational/. The compatibility
  default DB remains available to old entry points.
- market_data/kite_stream.py still constructs DuckDBStore() directly.
- scripts/run_paper_loop.py also constructs DuckDBStore() directly, captures
  chains in a background thread, captures spot data, and reads persisted chains
  through the same store. It is NOT a capture-independent service consumer.
- warehouse_exports.py exports Parquet through existing store connections, but
  this inspected helper is not itself a versioned immutable manifest publisher.

Thus the factory existing in the repository does not prove that the live
multi-terminal runners have migrated. No such migration is claimed by this ZIP.
The project-file snapshot of the paper runner was older; the findings above use
remote pinned source, not that snapshot.

Source blobs read remotely:
- store_factory.py: 679892ff5259f338da756944088b170bee1168e3
- store_paths.py: 6c8749810d77d9f79382c7e3a9034e4dc804ee2a
- warehouse_exports.py: df9e55c927e60b40240d2a3b2705f9f61fb7ac80
- kite_stream.py: 97460075aba32ff21c44e1f15195bb9aab5cdb46
- scripts/run_paper_loop.py: 7d67bdcee79825f5c972fd86c7379003d3ddc469

## This increment

AnalyticalSession supplies a process-owned in-memory DuckDB session over exact,
SHA-256-pinned immutable Parquet. It never opens an operational DuckDB file.
It has strict memory/thread/result bounds, unique process/role spill directories,
PID and serialization guards, explicit close, and source-pin verification before
and after reads. It returns bounded rows rather than a freely shared connection.

Use configured TRADING_DATA_ROOT (explicit Path or environment). No hard-coded
Windows/Linux data roots. Defaults are 256 MB DuckDB memory and one query thread
per analytical session, not permission for every terminal to use all cores.
These are DuckDB engine budgets, not a hard total-RSS cap on Python/Arrow/Polars.
Budget the sum across all active processes. Materialization and file hashing have
costs; this correctness-oriented pinned reader is not a low-latency tick API.

Connections are not shared or serialized across processes. Snapshot immutability
is a publication contract: this reader detects pin/stat changes but is not an OS
sandbox or proof against an attacker changing all trust anchors. There is no new
persistence framework or replacement for the existing Bronze/Audit APIs.

## Tests and Quack probe

The critical selection spawns an independent synthetic stream writer and three
snapshot-reader fixture processes (paper_reader, dashboard, research). It also
checks that read_only=True does NOT bypass the active native writer's file lock.
These fixture roles are not the actual Kite, paper broker, or Dash processes.

The explicit Quack probe uses only a new temporary DB and localhost ephemeral
port. It runs one native file-owning server and three separate clients, verifies
writer progress and denied DELETE, and cleans up processes/stores. It has an
exact SQL allowlist for two fixed probe operations, not an unsafe SELECT-prefix
filter and not general production RBAC. No broker/provider is imported.

The probe loads only an already installed, matching Quack extension. There is no
INSTALL/download or activation. If necessary, NSE_QUANT_QUACK_EXTENSION can point
to an operator-reviewed local .duckdb_extension file matching the DuckDB runtime.
Dependency declarations alone do not establish successful native extension load.

Exit: 0 passed capability probe; 3 unavailable runtime/extension; 2 failed probe.
A passed probe explicitly reports operational_wiring_validated=false. It does
NOT authorize source switching or certify the current app runners.

## Remaining operational cutover

1. Validate the real installed DuckDB 2.x + matching Quack bundle on Windows and
   Linux, not only this synthetic probe or mock-based tests.
2. Introduce a reviewed storage-service adapter and server-side role enforcement
   before exposing mutable datasets. Never rely on a client read_only flag or a
   SQL-prefix regex as production read-only authorization.
3. Migrate stream capture to its single designated owner. Remove duplicate paper
   capture only in the separately tested runner migration, preserving genuine
   quote timestamps, provider fixes, snapshot identity/completeness and controls.
4. Migrate paper market reads and decision/order repositories explicitly, with
   service/snapshot freshness fail-closed behavior; never fall back to a locked
   live file or let the paper process recapture implicitly.
5. Run the actual capture + paper loop + Dash + research concurrency acceptance,
   failure/restart and paper-cycle validation with isolated fixtures first.

This package intentionally does not claim any of steps 1-5 complete. It makes
the architecture clarification and the first testable analytical/probe boundary
executable without switching a running trading process to unvalidated transport.

## Charter clarification

The installer proposes charter 1.1.1 through exact, guarded text edits with full
original-file backup. It preserves process separation, one writer per physical
file and logical dataset ownership. Quack stays validation-gated. This is not a
live-trading permission change. Before apply, the repository charter is unchanged.

## Authoritative technical basis

- DuckDB concurrency: https://duckdb.org/docs/current/connect/concurrency
- DuckDB Quack 2.0 reference: https://duckdb.org/docs/2.0/quack/reference
- Quack security: https://duckdb.org/docs/current/quack/security

Stage 1 and S2 remain IN PROGRESS. No VIX history splicing, Gold admission,
provisional-regime promotion, scheduling, capture activation or broker change.

## Quack probe setup on Windows

From the repository root, provision the DuckDB extensions once in the project
environment. These are DuckDB extensions, not new Python dependencies; this
setup does not require changes to `pyproject.toml` or `uv.lock`.

```powershell
uv run python -c "import duckdb; con = duckdb.connect(':memory:'); con.execute('INSTALL quack'); con.execute('INSTALL httpfs'); con.close()"
```

The probe does not install extensions at runtime. The spawned server worker
loads `httpfs` on the same DuckDB connection before calling `quack_serve`.
Run the probe with:

```powershell
uv run python -m nse_quant.persistence.quack_probe
$LASTEXITCODE
```

A successful run reports `"status": "passed"` and exits `0`. The probe uses
a temporary store and a loopback endpoint; it does not open operational stores.

Validation recorded on 2026-11-24: Windows `windows_amd64`, DuckDB `2.0.0`,
and `quack:127.0.0.1:<port>`. All three separate probe clients
(`paper_reader`, `dashboard`, and `research`) passed and observed writer
progress. The server finished at generation 29.

This validates the synthetic transport probe only.
`operational_wiring_validated` and `decision_eligibility_asserted` remain
`false`. The opt-in service adapter and runner migration are separate changes.