# Verified research-publication snapshot consumer

## Baseline and actual-source reconciliation
User reports QA/tests passed, but repeated truncated Git line still identifies
fe4853d (the earlier recovery milestone). No newer publication commit hash is
established. Current uploaded quote_bundle_publication.py and its documentation
ARE present and were inspected: exact 20-column record, attempt fingerprints,
version/purpose/clock semantics and post-commit publication lifecycle.
Local HEAD/branch cannot be independently accessed. Preserve all newer committed
Ruff/mypy fixes; no existing file is overwritten by this package.

## Add only
src/nse_quant/data_platform/quote_publication_reader.py
src/nse_quant/data_platform/quote_publication_inspect_cli.py
scripts/inspect/inspect_research_quote_publication.py
tests/data_platform/test_quote_publication_reader.py
tests/data_platform/test_quote_publication_inspect_cli.py
docs/RESEARCH_QUOTE_CONSUMPTION.md

## Implemented
Read-only explicit-pin consumption of exact archived RESEARCH_ONLY snapshots.
Checks schema/contract/version/purpose/identity, bounded immutable BLOB content,
member counts/hashes and all linked audit evidence. Requires full successful
PLANNED/RUNNING/STAGED/VALIDATED/PUBLISHED/SUCCEEDED sequence for original publication;
a later success cannot substitute for failed origin approval/clock. Pending linked
attempts block. No audit repair, publication, source lookup or filesystem root read.
The original root may be absent; provenance text is not used as a live path.

API:
read_research_publication(publications, publication_id=<exact SHA256>)

Returns ResearchPublicationEvidence with verified_research_snapshot status only
for valid research records, immutable bundle, original clocks and audit identities.
No generic current/decision eligibility is implied. Source-current, availability,
historical-validity and decision-eligibility assertions remain False.
See docs/RESEARCH_QUOTE_CONSUMPTION.md for precise trust/time/replay boundaries.

CLI plan:
uv run python scripts/inspect/inspect_research_quote_publication.py --publication-db <research-publications.duckdb> --publication-id <64-lowercase-hex>

Append --inspect for a read-only bounded summary, not a raw feature dump.
No actor, credentials, current source DBs or artifact root needed. Default creates/
opens nothing and imports no execution service. No write/time-travel switches.

## Safe apply / mandatory QA
Inspect git branch --show-current, git log -1 and git status --short in
C:\Projects\nse_quant_platform. Require feat/medallion-feature-store; reconcile
actual publication writer/commit (not inferred from repeated fe4853d) without
resetting/discarding work. Verify the prior publication writer is installed.
Copy ONLY six repository additions; STOP if any target exists and compare instead.
Run verify-local.ps1 from extracted bundle. Review untracked files separately.
No deps, architecture, typing rules, configs or existing tests weakened/modified.

## Verification disclosure
44 focused tests passed under Python 3.12.8 using actual DuckDB registry snapshots
and actual read-only CLI/DB clones. Coverage: archive/root independence, exact
content/policy/approvals, full lifecycle vs latest-success, pending/failed origin,
retry integrity, corruption/bounds, timezone-invariant clocks/fingerprints, escaped
catalogs, missing registries, safe CLI plans and blocked/summary outcomes.
Tests use exact-column schema fixtures, not production writer execution. Baseline
codec/model interfaces used a materialized harness for sandbox execution; those
harness dependencies are NOT delivered. Real repository tests import committed
modules and existing codec tests remain intact. No full writer/source pipeline,
audit-as-of replay, current freshness or temporal admission is claimed. Full QA,
Ruff and mypy were not run here; local checks remain mandatory. Python line length,
static imports, staged patch whitespace and archive/file hashes were verified.

Suggested commit after local QA:
feat(data-platform): verify archived research quote-publication snapshots

Next boundaries: explicit temporal/knowledge admission and native decision/replay
contracts, without confusing research publication clocks with availability or
validity. Data loading/migration remains deferred.
