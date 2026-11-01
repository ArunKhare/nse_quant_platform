# Audited native Gold quote build persistence

## Baseline / source reconciliation
User baseline 835747d, QA/test passed and local/origin aligned by supplied log.
Local repository/HEAD cannot be independently accessed here.
Current uploaded audit.py, contracts.py and manifests.py were inspected. Gold
kernel lookup failed once and a retry returned unrelated audit source, so its
newly committed uploaded contents were NOT independently obtained. This package
uses the exact GoldQuoteCandidate, DEFINITION, FEATURE_VERSION and builder API
from the preceding delivered kernel that the user reported committed/QA-passed.
Verify those local APIs before application. No existing source or typing fixes
are overwritten. On any discrepancy stop, inspect and adapt deliberately.

## Repository additions
src/nse_quant/data_platform/gold_quote_store.py
src/nse_quant/data_platform/gold_quote_build_cli.py
scripts/ingest/build_gold_quote_prices.py
tests/data_platform/test_gold_quote_store.py
tests/data_platform/test_gold_quote_build_cli.py
docs/GOLD_QUOTE_STORAGE.md

## Public service
persist_quote_price_build(bronze, frame_silver, reference_silver, assessments, gold,
    assessment_revision_id=<exact SHA256>, actor_id=..., code_revision=...,
    initialize=False)

Caller owns four read-only input connections and a separate single-owner writable
Gold connection, with no enclosing transaction. Frame/reference Silver may share.
Every attempt freshly invokes the source-verifying Gold kernel. Definitions,
immutable candidate/blocked builds and attempt links are saved atomically.
Exact retries deduplicate content but append audit attempts. Changed results
retain invalidation history without deleting old evidence. All recording times
are separate from unknown publication/economic-validity times.
See docs/GOLD_QUOTE_STORAGE.md for schema, identities, audit gap and consumer limits.

## CLI (PowerShell)
Plan only:
uv run python scripts/ingest/build_gold_quote_prices.py --bronze-db <bronze.duckdb> --frame-silver-db <frames.duckdb> --reference-silver-db <references.duckdb> --assessment-db <assessments.duckdb> --gold-db <new-gold.duckdb> --assessment-revision-id <64-lowercase-hex>

Execution adds --execute --actor <actor> --code-revision <revision>.
New dedicated Gold DB also requires --initialize. Parent directory must exist.
Default plan opens/creates no DBs, makes no network/credential lookup and does
not initialize schemas. All source connections are read-only in execution.
CLI exit 0/COMMITTED can contain status=blocked: it is build execution success,
NOT publication or decision eligibility. Failures expose only a bounded reason.

## Apply safely and mandatory local QA
In C:\Projects\nse_quant_platform inspect git branch --show-current, git log -1
and git status --short. Require feat/medallion-feature-store; reconcile 835747d or
newer without resetting work. Compare local Gold kernel API/definition/hash/model.
Copy ONLY the six repository additions. STOP if any destination exists; compare
rather than overwrite. Keep bundle support files outside repository paths.
Run verify-local.ps1 from extracted bundle; it runs both new test files and then
all five mandatory QA commands. Review untracked additions separately.
No dependencies, architectures, typing rules, configs or existing tests changed.

## Verified here (and limits)
40 focused tests passed under Python 3.12.8 with actual DuckDB SQL/transactions.
Tests cover definitions, values/NULL times, retries, blocked history, audit failures,
rollback, tamper/version/schema checks, size/history limits, dedicated DB/alias
checks, quoted catalogs, and CLI plan/read-only/error/cleanup behavior.
Candidate computation is substituted at the persistence boundary. Sandbox baseline
AuditLedger/contracts were reconstructed from inspected source with condensed
formatting/diagnostics, and kernel model/definition interfaces replicated from
conversation. Those harness dependencies are NOT delivered. Repository tests
import actual committed modules. No end-to-end source-chain pass is claimed.
Full required repository suites, Ruff and mypy were not run here; local QA required.
Python line-length, staged patch whitespace and ZIP/file checksums were checked.

Suggested commit after local QA:
feat(data-platform): persist audited native Gold quote builds

Migration remains deferred. Next package: read-only verified Gold consumption.
