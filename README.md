# Read-only persisted packet association consumer @1

## Source baseline and reconciliation
User baseline ae4d0aa, reported QA passed, local and origin aligned.
This turn inspected actual uploaded packet_association_silver.py including the
corrected `for pin` variable, packet_reference_association.py and
reference_supersession.py. Consumer matches schema version 1, input/result
fingerprints, linked-attempt tables and dataset contract. Existing files untouched.
Local Git checkout/HEAD was not accessible; reconcile before applying.

## Add only
src/nse_quant/data_platform/packet_association_reader.py
tests/data_platform/test_packet_association_reader.py

## API
read_packet_assessment(bronze, frame_silver, reference_silver, assessments,
    assessment_revision_id=<exact lowercase SHA256>)
All connections are caller-owned, read-only, without enclosing transactions.
Assessment DB must be separate from every input. Frame/reference Silver may share.
No new CLI or DB schemas; no initialization, write, migration or audit transition.

## Behavior
Read schema, history, chosen assessment, contract and linked attempt audits in ONE
assessment-database transaction. Resolve the FULL group graph before status,
version, quality or audit filtering. New blocked/unsupported/failed rows can
invalidate old evidence; no old-good fallback, latest-wins or automatic pin change.
Cycles, duplicate/dangling links, multiple heads and exceeded bounds block.

For the active explicit pin verify the dataset contract, supported versions,
recomputed input/revision identities, bounded strict canonical JSON and association
fingerprint, duplicated row metadata and NULL publication/effective fields.
Require a link for first_job_id and validate command/scope/config/latest state for
EVERY linked attempt on this active pin. All must be terminal; at least one must
be SUCCEEDED. Terminal FAILED/CANCELLED attempts remain evidence, not success.
Unsupported or nonterminal audit states block even alongside a successful attempt.
Unlinked jobs and superseded rows' attempt audits do not grant authority; the graph
is already resolved without using their job states to filter invalidation edges.

Then recompute association using the existing source-verifying service. Require
exact canonical agreement with the stored result. Changed source evidence blocks;
no rewrite or reassessment occurs. Missing/changed schemas/catalogs or reader SQL/
execution failures propagate, not fabricated success. Invalid pin raises ValueError.
Expected evidence failures return a bounded blocked result with no association.

A verified_current result means stored evidence matches the current recomputation,
NOT that the association domain status is associated. Its nested association may
be blocked/ambiguous/unresolved and remains that exact disposition. Publication,
historical validity and decision eligibility remain False at the consumer boundary.
All linked successful job IDs and a deterministic snapshot evidence fingerprint
are returned, not persisted. Fingerprints can change as retry audits accumulate.

## Strict incomplete-attempt policy
If a domain commit was followed by final audit failure, that linked job may remain
RUNNING. A successful retry does NOT erase it: this consumer blocks while ANY
linked active-pin attempt remains nonterminal. It does not automatically repair
or manufacture success for that job. Review/recovery is separate future work.
Terminal failed attempts plus at least one valid success are permitted for exactly
the same content-addressed assessment. Failed executions without domain links are
not treated as assessment evidence; current source recomputation remains mandatory.

## Limits
Bounded at 1001 assessment nodes, 1000 links per node, 100000 link-JSON bytes,
1000 active-pin attempts, and 1 MiB chosen result JSON. Limits fail closed.
Database snapshot + subsequent source reads are not an atomic cross-database
snapshot, lock, immutable manifest or decision/publication barrier. Changes after
reads remain possible. Caller connection access modes remain a responsibility.
No temporal admission, feature publication or decision-loop integration is added.

## Safe apply and QA
Inspect git branch --show-current, git log -1 and git status --short in
C:\Projects\nse_quant_platform. Require feat/medallion-feature-store; reconcile
against ae4d0aa without resetting newer work. Add only the two repository files.
STOP if either path exists; compare rather than overwrite committed sources.
Run verify-local.ps1 from extracted bundle; it displays HEAD/runtime and executes
all five required QA commands. Review untracked additions as well as git diff.
No dependency, typing policy, architecture or existing tests are weakened.

## Verification disclosure
34 focused tests passed under Python 3.12.8 with actual DuckDB snapshots/SQL,
including unchanged hashes of a file-backed read-only assessment DB. Tests cover
invalidation regardless of quality/audit state, malformed graph/results, attempts,
source drift, error propagation and limits. Current association computation is
substituted, not an end-to-end provider/normalizer integration test.
Because execution cannot read Project Files directly, sandbox graph logic/model
interfaces were materialized from inspected source with condensed formatting;
store constants were replicated. Those harness files are NOT shipped. Repository
tests import actual committed dependencies. Ruff, mypy and full checkout QA were
NOT run here and remain mandatory locally. See VERIFICATION.json.

Suggested commit:
feat(data-platform): add invalidation-aware persisted association consumer
