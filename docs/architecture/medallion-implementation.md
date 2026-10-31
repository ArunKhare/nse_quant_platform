# Implementation and migration plan

Status: proposed rollout with Patch A1 foundation implemented in this bundle.
No production tables, capture hooks, backfill scripts or trading settings are changed.

## 1. First patch: implemented boundaries

New package: nse_quant.data_platform.
- contracts.py: immutable dataset contracts, layer-policy/metadata validation,
  canonical JSON and SHA-256 fingerprint.
- audit.py: explicit audit schema initialization, immutable same-version contract
  registration, append-only job/event API, parent linkage and lifecycle validation.
- inspect CLI: explicit --db, read-only connection, no initialization.
- tests: real disposable DuckDB tests, no project-store substitution.

Foundation tables live in medallion_audit schema:
- schema_versions(version PK, applied_at)
- dataset_contracts(dataset_name + contract_version PK, fingerprint, JSON, registered_at)
- jobs(job_id PK, parent, command, actor, scope_ref, code revision, config hash, created_at)
- job_events(job_id + event_index PK, state, recorded_at, reason_code)

Only schema version 1 is accepted. Future migrations require reviewed versioned
migration scripts. CREATE IF NOT EXISTS is not a complete schema drift validator;
pre-existing unexpected object definitions still require validation before production.

Job metadata uses identifiers, not arbitrary arguments or exception text. A failed
operation records a reason code. Full diagnostic logs must have their own redaction
policy and are not implemented here. Callers must not put secrets in identifier fields.

The single-owner API lock protects one ledger instance only. It is not interprocess
locking, an authorization mechanism, or a tamper-proof ledger. Caller owns connection.
Do not share it with other writer instances or an outer transaction. No update/delete
methods are exposed, but direct SQL remains possible with database access.

execution() records RUNNING -> SUCCEEDED for simple operations; publication jobs must
explicitly mark STAGED -> VALIDATED -> PUBLISHED inside it. State transitions do not
prove an artifact was actually published. Output manifests, command-specific success
requirements, crash reconciliation, counters, worker identities and fencing remain
future work. Do not mark terminal states manually inside execution().

## 2. Apply the bundle

Review new namespace and files against local HEAD before extracting. The repository
snapshots did not establish whether a local data_platform package already exists.
Do not overwrite local files with the same names without review.

Extract src/, scripts/, tests/ and docs/ into the repository root. No dependencies
are added: the project already requires Python >=3.12, DuckDB and pytest for development.
No initializer runs on import or read-only inspection.

Run locally:

    uv run pytest tests/data_platform/test_foundation.py -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect/inspect_medallion_audit.py tests/data_platform
    uv run mypy
    git diff --check

Example in a disposable in-memory DB (not the live store):

```python
import duckdb
from nse_quant.data_platform.audit import AuditLedger

conn = duckdb.connect(":memory:")
ledger = AuditLedger(conn)
ledger.initialize()
job_id = ledger.plan_job(
    command_name="test.foundation", actor_id="developer",
    scope_ref="reviewed-scope-1", code_revision="your-commit",
    config_hash="your-sanitized-config-hash",
)
with ledger.execution(job_id):
    pass
conn.close()
```

For an existing closed audit database:

    uv run python scripts/inspect/inspect_medallion_audit.py --db path/to/audit.duckdb

Do not open an active writer's database from an unrelated inspection process; use a
closed snapshot or the future owner-service API. No live-data smoke command is provided.

## 3. Work packages and dependencies

A1 (this bundle): contracts + audit primitives + architecture + seed inventory.
A2: complete local command discovery, command registry, immutable scope manifests,
    write-mode validation, planned change counts, runner integration, monitoring.
FS1: append-only capture journal, observation IDs, acquisition manifests, retry/conflict
     policy, durable checkpoints, source ownership and backup/restore tests.
FS2: Silver normalization and revision model, stable instruments, quality/quarantine,
     timestamp/session contracts, immutable input snapshots.
S1: full-key IV/Greek mutation fixes; source-preserving ATM history; NIFTY bootstrap
    guard. Until migrated, prohibit unsafe maintenance against the active database.
FS3: Gold feature definitions/builds, input lineage, coherent IV/Greeks, staged validation,
     transactional publication and outbox/reconciliation.
S2: source-aware candle rebuilds, scoped completed-session RV, warm-up handling and
    explicitly versioned analytical formula corrections.
FS4: availability-aware retrieval, invalidations/TTL, decision bundles, exact replay.
E1: artifact manifests, unique staging names, validation, versioned publication,
    explicit active-policy promotion and symbol isolation.
R1: consolidate acquisition/orchestration, migrate callers, retire unused entrypoints.
OPS1: performance, failure injection, retention, disaster recovery and runbooks.

A1 is not a prerequisite to emergency guards in S1: ship targeted safety fixes early,
but keep their behavior changes separate from structural refactors.

## 4. Legacy migration

1. Stop uncontrolled maintenance writers; schedule a consistent backup under the
   database ownership model. Verify restore before schema changes.
2. Record local commit and full script/database inventory. Do not infer local state
   from archived Project Files or prior wrapper deletion discussions.
3. Assess historical mutations and classify provenance unknowns explicitly.
4. Import legacy datasets without claiming pristine Bronze provenance.
5. Begin genuinely raw ingestion at an explicit cutover/checkpoint.
6. Dual-build new derived versions without changing strategy consumers.
7. Compare outputs and investigate differences; freeze golden datasets.
8. Switch consumers under an approved feature-set version with rollback.
9. Disable legacy writers; retain original snapshots and exact decision evidence.
10. Delete wrappers only after repository and external scheduler reference audit.

## 5. Analytical changes requiring separate versions

- IV price policy, rate source, expiry instant and year basis alignment.
- Daily RV units/scaling and completed-session definition.
- Spot VWAP session reset, return boundaries and warm-up contract.
- Butterfly formula, IV/skew threshold units, tenor-pair aggregation.
- Regime full-sample vs point-in-time thresholds and availability timestamps.
- Replay timezone, run selection and original-vs-recomputed analytics.

Correcting code does not authorize overwriting old published builds.

## 6. Required transaction/publication design

A domain build commits staged rows, validation result, publication record and an audit
intent/outbox in one owner transaction where supported. An audit relay appends the
cross-job execution record. Reconciliation resolves a committed domain publication
whose audit delivery was interrupted. File builds use immutable versioned destinations
plus verified manifests; promotion is a separate audited pointer change.

No multi-resource transaction is implied by the A1 execution context manager.
On exception it records failure; the job must roll back/stage-clean its own domain work.

## 7. Acceptance gates

- Append preservation and exact retry/conflict tests.
- Scope/key/source/run isolation and historical version coexistence.
- Failure leaves prior published data intact.
- Future input/corrections cannot affect earlier as-known-at results.
- No invalidation resurrection or cross-expiry/run mixing.
- Boundary-aware bars/sessions, warm-up parity and deterministic calculations.
- No credentials in audit and no unregistered production mutation/export commands.
- Independent backup restore; crash/restart/outbox reconciliation.
- Load, memory, disk-full, retention and concurrent ownership tests.
- Exact consumed bundle replay and shadow-live comparison.

Production release requires explicit latency/freshness, RPO/RTO, volume, retention,
operating-environment and responsible-owner decisions. These are currently unresolved.

## 8. Suggested commit for this foundation

    feat(data-platform): add medallion contracts and audit foundation

Do not describe this commit as a completed feature store or production migration.
