# Daily and EOD replacements: audited legacy workspaces

Status: transitional implementation, not production feature-store completion.
This package replaces scripts/run_daily_research.py, scripts/eod_maintenance.py and
scripts/start_eod_maintenance.ps1. Backward CLI compatibility is deliberately not retained.

## Why isolated execution

Legacy RV/candle builders still replace tables and lack full date/source safeguards.
Wrapping those writes with an audit record would not make original observations safe.
These adapters instead pin an offline database snapshot, copy source code, and direct
all legacy writes into a new run-local database and filesystem workspace.

The adapter does NOT label existing tables Silver or its output Gold. It records the
execution model as offline_legacy_workspace and exported quality as UNASSESSED_LEGACY.
A source database copy is an immutable legacy input snapshot, not a pristine Bronze claim.

## Architecture and framework relationship

Reuse A1 AuditLedger and A2 ManifestStore. Each parent and child is audited. Step IDs
are part of child command identities and receipts. Each step binds actual checksummed
files from previous steps; mutable workspace DB inputs/outputs are preserved as
separate closed-database checkpoints. Source code is frozen and checked before use.

A2a's strict Category.BUILD requires already-classified Silver/Gold dataset inputs.
A2b preflights static scopes before any dynamic outputs exist. Neither contract should
be bypassed with fictional dataset names/snapshot IDs. This transitional adapter
therefore uses their underlying audit/manifest services directly; it does not claim
these legacy jobs have been migrated into the generic medallion command registry.
Replace these legacy services with native dataset builders as FS1/FS2/FS3 land.

## Execution lifecycle

1. Default invocation returns a nonmutating plan; no workspace, audit DB or subprocess.
2. Execution needs --execute --source-offline --code-revision.
3. Create a UUID-named exclusive run directory and its separate audit DB.
4. Reject a source WAL, acquire a read-only DuckDB connection, copy the checkpointed
   source DB and compare source/copy checksums. Never issue source update/DDL/checkpoint.
5. Keep source_snapshot.duckdb unchanged; use a separate working.duckdb.
6. Copy repository src/scripts into run-local code and verify matching file hashes.
7. Clone main/test YAML into workspace; remove secrets mapping, force offline safety,
   disable notifier, and point both configurations and subprocess environment at workspace.
8. Run audited child operations sequentially with actual input plans/output receipts.
9. Verify source checksum again. Save final run result and retain all intermediate evidence.

The offline acknowledgement is a policy acknowledgement, not collector management.
Stop collector/dashboard/maintenance writer processes yourself. DuckDB file locking
and WAL rejection provide additional failure checks. Do not copy a running database
with an external file-copy tool and pretend it is a consistent snapshot.

Whole-database snapshots preserve all history. Scope controls exports/research dates;
the stored snapshot is not a minimal/redacted data extract. Protect it accordingly.

## Daily workflow

Exports all available option dates in the requested walk-forward range into the
isolated warehouse, then exports regimes, evaluates readiness, runs walk-forward,
generates report, and attempts an optional digest. Required child nonzero exit stops
execution; digest failure is visible as SUCCEEDED_WITH_WARNINGS.

Readiness, experiment permission and insufficient-fold exits are not bypassed.
The inspected readiness implementation still uses a simplified IV-presence count
under the IV/RV alignment name. This adapter does not repair or certify that policy.
Actual IV/RV alignment and research-grade quality remain a separate safety patch.

The run ID is generated from the unique workspace directory, not an old caller value.
No shared registry, readiness JSON, report, or warehouse path is silently replaced.
The existing report loader is used; actual end-to-end fold/report compatibility must
be verified locally with representative data.

## EOD workflow

Runs legacy RV, daily candles and selected intraday intervals in the workspace only,
then exports options, latest daily regime, spot candles and daily RV with row counts,
schemas and hashes in an export manifest. --skip-export skips only Parquet export.

The legacy RV script rebuilds all available dates. That broad scope is explicitly
recorded as all_available_dates_in_isolated_workspace; it does not alter original RV.
This is not a falsely scoped one-day repair. Analytical formula changes are deferred.

No option data may yield explicitly EMPTY exports; this is not research-grade success.
No original no-option 'skip export' semantics are implied. Consumers must inspect quality.
A direct CLI invocation uses an explicit date and does not itself enforce trading-day
or session-completion eligibility. The supplied PowerShell execution launcher keeps a
trading-calendar check. Use only completed intended sessions; completeness enforcement
is a future native-builder requirement. Notifications are intentionally disabled.

## New CLI examples: plan only

From repository root, using an existing source database and explicit dates:

    uv run python scripts/eod_maintenance.py --source-db data/nse_quant.duckdb --trade-date 2026-10-30
    uv run python scripts/run_daily_research.py --source-db data/nse_quant.duckdb --date 2026-10-30 --walk-forward-start 2026-10-20

Only after local validation and stopping source writers:

    uv run python scripts/eod_maintenance.py --source-db data/nse_quant.duckdb --trade-date 2026-10-30 --execute --source-offline --code-revision YOUR_COMMIT

These are local commands, not instructions to execute an unreviewed package on live data.
Start with a disposable database fixture. No automatic promotion into live tables occurs.

PowerShell launcher:

    ./scripts/start_eod_maintenance.ps1 -SourceDb data/nse_quant.duckdb -TradeDate 2026-10-30

Execute adds -Execute -SourceOffline -CodeRevision YOUR_COMMIT. Old InstrumentToken,
shared export/output directory and run-id flags are removed. Existing scheduled jobs
must be updated; do not assume old launch commands remain compatible.

## Artifacts

Each run directory includes audit.duckdb, manifests/, source_snapshot.duckdb,
working.duckdb, code/, config/, checkpoints/, command_plans/, logs/, data/ and result JSON.
Plans identify step scope, actual input hashes, command arguments, parent/child IDs
and calculation parameters. Export manifests carry actual schemas/row counts/hashes.
Source archives and logs can contain sensitive business data; restrict access and
retention. Generic inherited broker/Telegram secret environment prefixes are removed,
but this is not a comprehensive secret scanner or sandbox. Do not share archives blindly.

No output is published to the central operational dataset. Downstream consumers must
use the explicit successful run's artifacts, not 'latest file found'. Check both audit
state and workflow receipt; an interrupted finalization can leave mismatched artifacts.

## Failure/recovery limits

Completed workspace children are not rolled back. A failed run stays isolated for
inspection, and the next attempt creates a different workspace. No automatic resume,
retry controller, distributed lock, fencing, timeout, disk quota or atomic cross-resource
commit is provided. Handle failed final audit/publication via manual reconciliation.

A failed export can leave partial files inside that failed run. They do not replace
prior good runs. Readers must not treat uncommitted run directories as published.
Source write prevention depends on supported offline execution and reviewed executors,
not hostile-process isolation. Source hash changes cause failure, not restoration.

Snapshots and per-step DB checkpoints multiply disk usage substantially; estimate
capacity before execution. Disk-full tests and quotas remain required before production.
The source-path/code snapshot protections do not make a malicious repository safe.

## Existing test imports

Two small shared helpers remain re-exported from the thin EOD entrypoint because
existing readiness tests import them. They delegate to the new package implementation;
they are not legacy execution wrappers. No obsolete candle/export scripts are invoked.

## Retire duplicate orchestration

The uploaded tree also had src/nse_quant/research/run_daily_research.py containing
module-scope old orchestration. Search callers before removing it:

    git grep -n 'nse_quant.research.run_daily_research' -- .

If no required caller remains, retire it in this integration commit:

    git rm src/nse_quant/research/run_daily_research.py

Do not delete other distinct builders/backfills. A ZIP cannot itself remove tracked
files; perform and review this Git removal locally. No deletion is claimed here.

## Local QA

    uv run pytest tests/data_platform -q
    uv run pytest tests/test_backtest_readiness.py -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/run_daily_research.py scripts/eod_maintenance.py tests/data_platform
    uv run mypy
    git diff --check

After review, run actual EOD and daily smoke tests on a disposable representative copy.
Verify no source byte changes, expected row counts, parent-child receipts, original
configuration safety, and no outputs outside the run root. Test launcher on Windows.

## Suggested commit

refactor(workflows): isolate and audit daily and EOD execution
