# Audited append-only packet/reference assessments

## Baseline and reconciliation
User baseline b378d92: association implementation committed, local/origin aligned,
QA passed. Local repository/HEAD could not be accessed here.
Inspected Project Files audit.py, contracts.py and native_reference_silver.py.
AuditLedger.execution commits lifecycle independently; domain rollback belongs
to the service. DatasetContract Silver requires revision_id, source_observation_id,
and recorded_at with APPEND_REVISIONS. This package uses those native APIs.
The newly committed association/frame-reader source is absent from the returned
upload snapshot; their interfaces are grounded in this conversation, not a local
HEAD inspection. Stop on discrepancies before apply. Existing files untouched.

## Repository additions
src/nse_quant/data_platform/packet_association_silver.py
src/nse_quant/data_platform/packet_association_cli.py
scripts/ingest/assess_packet_reference.py
tests/data_platform/test_packet_association_silver.py
tests/data_platform/test_packet_association_cli.py

## Purpose/API
persist_packet_association(bronze, frame_silver, reference_silver, target,
    frame_revision_id=..., packet_ordinal=...,
    reference_assessment_revision_id=..., actor_id=..., code_revision=...,
    initialize=False)

Three owned read-only input connections, separate single-owner writable output,
no enclosing transactions. Frame and reference inputs may share a Silver file.
Output must be separate from ALL inputs; same connection/file checks include
attached databases. Output permits Silver/audit schemas only, never legacy tables.
Only explicit initialization creates new schemas. No adapter or legacy DB write.

## Stored objects (schema version 1)
silver.packet_reference_schema_versions
silver.packet_reference_assessments
silver.packet_reference_attempts

The result is freshly computed under an audited attempt, never supplied as an
arbitrary import. Full association evidence is canonicalized and fingerprint
checked. Pins, versions and status are stored with exact result JSON. Publication
and effective endpoints remain NULL; no eligibility is asserted.

Input identity hashes explicit frame/ordinal/reference pins plus store/association
versions. Assessment revision hashes input identity and association fingerprint.
Exact result retry reuses its assessment and appends a new job/attempt. Changed
results append revisions linking all bounded prior assessments for that input;
blocked/ambiguous/unresolved evidence is never filtered out. No UPDATE/DELETE
operations in this API. Retry detects deterministic-column/content mismatches.
History is bounded: at most 1000 prior assessment links for a new revision.
Exact retries remain possible at the bound. Attempts/audit grow append-only.

Each result/attempt-link write is atomic in one domain transaction. Audit planning,
RUNNING and terminal events are separate transactions by foundation design.
A domain row or attempt link alone DOES NOT prove audit completion. Final audit
failure leaves real committed evidence and a nonterminal job; no fabricated success,
automatic repair, truncation or audit transition is performed. A fresh retry gets
its own job; it does not rewrite the earlier job or first_job_id.

## Important consumer boundary
This package is NOT a persisted-assessment consumer/current-selection API.
Supersession links preserve invalidation-first history; never SELECT only associated
or successful rows before resolving invalidation evidence. An exact old result
reappearing after a newer assessment reuses its old revision and DOES NOT revive
it or override newer links. No automatic graph-head selection is provided.
A future consumer must validate the graph, all relevant attempt audits and current
source evidence. Do not admit stored assessments directly to decisions/replay.
Inputs are verified sequentially, NOT an atomic cross-database snapshot or a
publication barrier. Post-read source changes remain possible. Source reader limits
and acquisition/session-health limitations remain unchanged.

## CLI
Plan only (no execution imports, DB opens, writes, network or credentials):

uv run python scripts/ingest/assess_packet_reference.py --bronze-db <bronze.duckdb> --frame-silver-db <frames.duckdb> --reference-silver-db <reference.duckdb> --assessment-db <new-assessments.duckdb> --frame-revision-id <64hex> --packet-ordinal 0 --reference-assessment-revision-id <64hex>

Execution also requires --execute --actor <actor> --code-revision <revision>.
Add --initialize for a new dedicated output DB. Parent directory must exist.
No implicit DB creation in plan. Inputs always read-only. CLI diagnostics are
bounded generic failure codes, not arbitrary exception text or credentials.
Exit 0 means assessment execution committed, even for blocked domain evidence;
execution_status and domain status are intentionally distinct. Exit 1 means
execution failure; argument errors use argparse exit 2. No publication claim.

## Safe application/QA
Inspect local git branch --show-current, git log -1 and git status --short.
Require feat/medallion-feature-store, reconcile b378d92 or newer without resetting.
Check current association/AuditLedger signatures. Copy only the five repository
additions; STOP if any target exists and compare instead. Preserve prior Ruff fixes.
Run verify-local.ps1 from extracted bundle. Review untracked additions as well as
git diff: git diff --check alone does not inspect untracked files.
No dependencies, typing rules, existing tests or architecture were weakened.

## Verification disclosure
30 focused tests passed with actual DuckDB SQL/transactions and audit lifecycle
execution, including rollback, retries, evidence changes, tamper checks, schema/
size/history bounds, forbidden targets, same-file rejection and final audit failure.
Association computation is substituted in persistence tests; CLI tests cover
plan/input validation, not end-to-end successful CLI execution.
The sandbox lacks the actual checkout. Baseline AuditLedger/contracts were
reconstructed from inspected source with formatting/diagnostics condensed for
execution, and the association model was replicated with a fail-fast placeholder.
These harness dependencies are NOT included in this bundle. Tests in the real
repository import its actual modules. No full end-to-end source pipeline claim.
Full required repository suites, Ruff and mypy were NOT run here; local QA required.
See VERIFICATION.json and SHA256SUMS.json for performed checks.

Suggested commit:
feat(data-platform): persist audited append-only packet-reference assessments
