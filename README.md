# Nonexecuting targeted staged-bundle recovery plans

## Baseline / source reconciliation
User baseline 05de39c, QA/tests passed and local/origin aligned by supplied Git log.
Local HEAD/branch cannot be independently inspected. This turn inspected actual
quote_bundle_staging.py schema/scope/config, staging CLI/tests and existing bundle
contracts from context. Inspector is structurally independent of Gold/source
verification; it does not invoke the stage reader or claim current-source validity.
No committed staging/consumer/codec APIs, fixes or existing tests overwritten.

## Add only
src/nse_quant/data_platform/quote_bundle_recovery.py
src/nse_quant/data_platform/quote_bundle_recovery_cli.py
scripts/inspect/inspect_quote_bundle_recovery.py
tests/data_platform/test_quote_bundle_recovery.py
docs/QUOTE_BUNDLE_RECOVERY_PLANS.md

## Implemented
One explicit target: read-only metadata/contract/history/audit observations,
bounded artifact verification, orphan/missing/corrupt and incomplete-job review
findings, names-only bounded pending-file observations and immutable nonexecuting
plans. No delete, truncate, reseal, adopt, force-success, restore, migration or
publication code path. execution_permitted is always False. Limits/incomplete
coverage are reported; no global clean/healthy claim is made.

CLI plan only:
uv run python scripts/inspect/inspect_quote_bundle_recovery.py --staging-db <staging.duckdb> --artifact-root <bound-artifact-root> --bundle-id <64-lowercase-hex>

Append --inspect for read-only observations. Optional bounded --max-history,
--max-jobs, --max-directory-entries and --max-artifact-bytes tune inspection scope,
not recovery authority. Default plan imports no DB/execution service, opens/scans/
creates nothing and performs no network/credential lookup. Execution/repair flags
are intentionally rejected. Detailed policy in docs/QUOTE_BUNDLE_RECOVERY_PLANS.md.

NO_TARGET_FINDINGS is not an execution permit, global inventory or source check.
An intact orphan still requires separate review, and pending files are never
ingestible based on this plan. Use the committed stage consumer for current-source
verification. A separate future recovery operation would require fresh review and
explicit authorization; this package supplies no such executor.

## Safe apply / mandatory local QA
Inspect git branch --show-current, git log -1 and git status --short in
C:\Projects\nse_quant_platform. Require feat/medallion-feature-store; reconcile
05de39c or newer without resetting/discarding work. Copy ONLY five repository
additions. STOP if any path exists; compare rather than overwrite. Run the bundled
verify-local.ps1 from extracted location. Review untracked additions as well as
git diff. No dependencies, architecture, typing rules or existing tests weakened.

## Verification disclosure
28 focused tests passed under Python 3.12.8 with real DuckDB/file fixtures and a
read-only CLI clone whose database checksum stays unchanged. Tests cover healthy
scope vs global authority, orphan/missing/corrupt evidence preservation, pending
payload nonexposure, incomplete audit/first links, bounds, graph errors, legitimate
other stage jobs, default plan, rejected repair flags and redacted failures.
Sandbox baseline codec/model and graph dependencies used a materialized/interface
harness, NOT the full repository execution environment. Those harness files are
NOT shipped. New repository tests import actual committed dependencies; existing
codec/graph tests remain intact. No current-source or full recovery/publication
integration pass is claimed. Full required QA, Ruff and mypy were not run here;
local checks are mandatory. Line lengths, static imports, patch whitespace and ZIP
checksums were checked separately, not substituted for those tools.

Suggested commit after local QA:
feat(data-platform): add bounded nonexecuting quote-bundle recovery plans

Loading and migration remain deferred until all platform acceptance gates pass.
