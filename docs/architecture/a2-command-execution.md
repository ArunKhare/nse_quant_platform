# A2a: registered execution and immutable scope manifests

Status: additive implementation package. Requires the QA-passed A1 foundation.
This is the command-execution part of A2, not completed workflow migration.

## Implemented

- Explicit registered command name/version/owner/category and dataset read/write sets.
- Trusted executor binding; another executor/definition cannot silently replace the
  same in-process command version. Registry is in-memory; manifests preserve definition.
- Layer boundaries: ingest -> Bronze; normalize Bronze -> Silver; build Silver/Gold -> Gold.
- Export and inspect declare no domain writes. Workflows delegate all domain I/O.
- Immutable scopes: nonempty uppercase symbols, aware half-open timestamps [start,end),
  run identifiers, pinned input snapshot references. Equivalent instants canonicalize to UTC.
- Normalize/build/export require snapshot references. Ingest sources require richer
  source-file/capture manifests in a later adapter; inspect can query live state only
  under its approved read-consistency contract.
- Plan includes command contract, scope, actor, code/config identifiers and parent.
- Default dry-run serializes a plan only: no files, audit calls, or executor invocation.
- Non-dry run writes a content-addressed plan, starts an A1 job, calls its bound
  executor, validates the result type and basic category/count rules, and saves a
  job-linked receipt before completing the audit context.
- Nonzero subprocess codes cannot accidentally become success: raw integer return
  values are rejected. Adapters must raise on failed subprocess exit status.

## Files

src/nse_quant/data_platform/commands.py
src/nse_quant/data_platform/scopes.py
src/nse_quant/data_platform/manifests.py
src/nse_quant/data_platform/runner.py
tests/data_platform/test_command_runner.py
tests/data_platform/test_runner_integration.py

No A1 files, configs, domain tables, live collectors or legacy scripts are replaced.
No command is automatically registered or executed on import.

## Filesystem manifest contract

Store canonical JSON under SHA256.json. Publish via same-directory staging plus
an exclusive hard link. Existing equal content is an exact retry; unequal content
fails closed. read() verifies checksum. Staging is removed on handled failures.
No replacement fallback is used if hard links are unavailable on the filesystem.
Test this on the actual Windows volume. Directory fsync/power-loss guarantees,
external tampering, symlink attacks and filesystem permissions remain deployment
concerns; this is not a WORM archive or an adversarial filesystem sandbox.

## Execution/audit contract

Uses A1 public plan_job()/execution(). The existing audit database must already
be initialized by its owner. No constructor initializes or opens a database.
The caller supplies the owner ledger connection; do not create independent writers.

A scope_ref is sha256:<plan_id>; resolve it in the configured ManifestStore root.
Successful receipt contains job_id + plan_id + typed counts + output reference IDs.
Receipts are located by content hash; lookup/indexing by job is not yet a database
feature. Persist/index returned RunReport in the future owner API; the receipt also
carries its job ID for recovery scanning.

Every actual invocation creates a distinct job. Equal plans can be reused, but
this does not make domain side effects automatically idempotent. Executor-specific
retry keys/checkpoints are required before automatic retries.

Parent linkage is forwarded to A1; that ledger validates the parent exists.
There is no workflow scheduler, fan-out, timeout, retry controller or child-failure
aggregation in this package. Those are A2b and require current local workflow files.

## Failure semantics and limits

- Plan-write failure occurs before job creation; callback is not executed.
- Job creation failure can leave an unreferenced plan; no domain callback runs.
- Callback or receipt-write failure is recorded by A1 as failure when possible.
- A callback may already have domain effects when validation/audit fails: this
  runner does not roll them back. Callbacks need staging/transactions/outbox.
- Audit-finalization failure can leave a valid receipt with an incomplete audit job.
  Reconciliation is a later requirement; do not retry side effects blindly.
- Output references/counts are executor declarations, not independent dataset proof.
  Validated publication requires a later publisher/manifest validator.
- State proceeds RUNNING -> SUCCEEDED for this execution adapter. It does not claim
  STAGED/VALIDATED/PUBLISHED domain publication happened.
- Registry/scope checks are application contracts, not permissions or SQL interception.
  An untrusted callback can violate them. Migrate writers to constrained repositories.

## Safe integration sequence

1. Apply A2a and run all A1/A2 tests locally.
2. Register one nonmutating inspector with explicit read scope.
3. Integrate one export with pinned inputs and a versioned destination, no overwrite.
4. Add parent/child workflow orchestration against current local code, preserving
   fail-fast and nonblocking-step behavior explicitly.
5. Move writer logic behind source-preserving repositories before registering builds.
6. Require audit registration for production entrypoints and inventory exceptions.

Do not bind legacy option/RV/candle mutators to new Gold names merely to bypass
registration rules. Source-preservation safety patches remain separate.

## Validation

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform tests/data_platform
    uv run mypy
    git diff --check

Unit execution in this bundle: 26 tests passed using a recording ledger double.
Two integration cases against the real A1 ledger are included for local execution;
they were not run here because the QA-passed local A1 files were not available.
The inspector/EOD files returned by repository exploration predate local migrations,
so they are intentionally not overwritten.

## Next commit after local QA

feat(data-platform): register commands and audit scoped execution
