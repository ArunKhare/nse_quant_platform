# Audited explicit research-only quote publication

## Baseline and requested fix check
User baseline fe4853d, QA/test passed, HEAD/origin aligned by supplied Git output.
Local HEAD/branch cannot be independently inspected. Current uploaded recovery
module/CLI/tests and staged consumer were inspected. The committed recovery code
now explicitly annotates steps: tuple[str, ...] for different-length review tuples,
along with consolidated/formatted conditions. DEFAULT_RECOVERY_POLICY remains the
function default; coverage and nonexecution flags are intact. Those corrected files
are not regenerated or overwritten. Actual current source is authoritative.

## Add only
src/nse_quant/data_platform/quote_bundle_publication.py
src/nse_quant/data_platform/quote_publication_cli.py
scripts/ingest/publish_research_quote_bundle.py
tests/data_platform/test_quote_bundle_publication.py
tests/data_platform/test_quote_publication_cli.py
docs/RESEARCH_QUOTE_PUBLICATION.md

## Purpose of this increment
Native audited publication registry writer, explicitly RESEARCH_ONLY. Fresh stage
verification is bound to an exact reviewed evidence fingerprint, checked twice.
Store immutable exact bundle bytes and a separate new platform record-clock
publication envelope. Preserve all source/staged bytes/times. No decision purpose,
economic-validity inference, repair, migration, acquisition or latest selection.
No recovery NO_TARGET_FINDINGS result grants publication authority.

This is not all data_platform completion. No verified publication reader or temporal
admission/decision/replay integration is included yet; raw registry rows must not
be used directly by consumers. Documentation explains the clock and audit gaps.

## API and plan-first CLI
Use read_staged_quote_bundle to obtain/review the exact evidence fingerprint for
the intended bundle/root. Passing an arbitrary fingerprint does not grant validity;
the native reader must return the same current fingerprint during both checks.

Plan:
uv run python scripts/ingest/publish_research_quote_bundle.py --bronze-db <bronze.duckdb> --frame-silver-db <frames.duckdb> --reference-silver-db <references.duckdb> --assessment-db <assessments.duckdb> --gold-db <gold.duckdb> --staging-db <staging.duckdb> --publication-db <research-publications.duckdb> --artifact-root <bound-root> --bundle-id <64hex> --expected-stage-fingerprint <reviewed-64hex> --purpose RESEARCH_ONLY

Execution adds --execute --allow-publication --actor <actor> --code-revision <revision>.
New dedicated publication DB requires --initialize; its parent directory must exist.
All six inputs are read-only; no artifact files or upstream records are written.
Purpose has no default and no decision/trading choice. Both execution intent flags
are required before DB connections. These are intent/ownership gates, not ACL/auth.

Successful execution records legitimate PUBLISHED then SUCCEEDED audit events only
after committing publication bytes/attempt. Exact retries preserve original record
clock and first approval. Incomplete/no-success publication history blocks ordinary
retry for reviewed recovery, not force-success. See docs/RESEARCH_QUOTE_PUBLICATION.md.

## Mandatory local apply/QA
Inspect git branch --show-current, git log -1 and git status --short in
C:\Projects\nse_quant_platform. Require feat/medallion-feature-store and reconcile
fe4853d or newer without resetting work. Copy only six repository additions; STOP
on existing paths and compare. Preserve the committed Ruff/mypy corrections.
Run verify-local.ps1 from extracted bundle. Review untracked additions as well as
git diff. No deps, typing rules, configs or existing tests weakened/modified.

## Verification disclosure
40 focused tests passed under Python 3.12.8 with actual DuckDB publication/audit
transactions. Covers exact snapshots/false eligibility, legit lifecycle, retries/
original clock, reviewed pin and second-pass drift, rollback, incomplete final audit
review, tampering, versions/roles, quoted catalogs and non-UTC session retries.
CLI tests cover no-I/O plan, both flags, purpose rejection, exact forwarding,
read-only inputs, cleanup and redacted failures. Stage verification is substituted;
CLI execution substitutes the publisher separately for connection-boundary checks.
Sandbox baseline audit/contracts were reconstructed from inspected context and
codec/models replicated with interface-level behavior. Harness files NOT shipped.
Actual repository tests import committed modules; no full source/publication or
crash/point-in-time admission pass is claimed. Required full QA, Ruff and mypy were
not run here and remain mandatory locally. Line-length/static import/patch whitespace
and archive/file checksums were checked, not substituted for those tools.

Suggested commit after local QA:
feat(data-platform): publish audited research-only quote bundle snapshots

Loading and migration remain deferred until all acceptance gates pass.
