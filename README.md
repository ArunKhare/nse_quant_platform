# Native reference lookup operational patch

## Scope
Additive read-only CLI over the existing FS2b3 lookup_native_reference API.
This is an operational inspection increment, not FS3, a feature publication,
canonical contract resolution, quote enrichment or decision-loop cutover.
No existing source files, dependencies, typing configuration or tests are replaced.

## Source reconciliation
Inspected uploaded pyproject.toml (Python >=3.12; Ruff py312), HTTP capture
kite-instrument-http@2 including DEFAULT_HTTP_POLICY and transfer-framing corrections,
native_reference_decode, native_reference_silver, native_reference_evidence,
native_reference_reader and reference_supersession. Offline CSV @1 remains distinct
from native CSV @1. Reader resolver is native-reference-consumer@1.
Uploaded drain_capture.py still uses ingest.kite_segments@1; it is stale relative
to reported committed health-gated @2. It is deliberately not in this patch.
Local HEAD/branch and complete source inventory were not accessible. No claim of
exact HEAD compatibility or absence of an unpublished equivalent CLI is made.

## Apply safely (PowerShell)
1. In C:\Projects\nse_quant_platform run git branch --show-current and git log -1.
   Require feat/medallion-feature-store. Review git status --short.
2. Inspect local native_reference_reader.py: lookup_native_reference must accept
   bronze, silver, assessment_revision_id and instrument_token and return the
   NativeReferenceLookup dataclass with status. Resolve discrepancies before apply.
3. Copy only the three files under src/, scripts/ and tests/ into matching paths.
   STOP if any destination already exists; compare it rather than overwrite.
   Do not copy README or verification scripts over repository files.
4. Run the supplied verify-local.ps1 from the extracted bundle, passing -Repository
   if needed. It verifies branch, displays HEAD/runtime and runs every required QA
   command. It does not change dependencies or repair failures automatically.
5. Review git diff and git status, including new untracked files, before committing.
   git diff --check alone does not inspect untracked files.

## Usage
Plan (no database connections, network, credentials or initialization):

uv run python scripts/inspect/inspect_native_reference_lookup.py --bronze-db <bronze.duckdb> --silver-db <silver.duckdb> --assessment-revision-id <64-lowercase-hex> --instrument-token 123

Append --execute to perform read-only verification using existing databases.
Exit 0: plan or matched. Exit 2: executed ambiguous/unresolved/blocked result,
or argparse input error (stderr distinguishes input errors). Exit 1: operational
failure, with bounded generic diagnostic and no raw exception text.
Lookup output retains the reader's reason, row pins and non-publication semantics.
No audit success is manufactured: this CLI writes neither audit nor data records.

## Limits
Calls the existing reader without replacing its integrity/supersession logic.
Bronze and Silver reads are separate snapshots, not an atomic cross-database
barrier. Evidence can change after inspection. No caching, batch atomicity,
historical validity, contract identity, feature eligibility or exact replay claim.
The existing reader can load up to its own MAX_RESULT_BYTES limit (128 MiB).
Filesystem path alias checks are safeguards, not protection against hostile
concurrent filesystem replacement. Use trusted local database paths.

## Verification
See VERIFICATION.json. Focused tests include real DuckDB read-only enforcement;
mocked reader tests verify orchestration, NOT full source/audit integrity.
Full local repository suites and Ruff/mypy remain required and were not run here.
