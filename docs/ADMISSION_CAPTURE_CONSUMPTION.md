# Archived native admission capture consumption @1

## Reconciliation

This additive package targets the uploaded admission_capture.py interface:
publication-admission-capture@1, capture.publication_admission@1, schema 1,
and research-publication-admission@1. It does not replace capture, policy,
AuditLedger, medallion contracts, existing tests, dependencies or pyproject.toml.
The uploaded pyproject requires Python >=3.12 (not exactly 3.12); the reported
local Python 3.14.2 remains subject to the actual local dependency/tool environment.
Uploaded snapshots do not establish local HEAD, branch, commit status or QA.
Last user-reported Git baseline remains 46a9a5e; newer capture commit is unverified.

## API

    read_admission_capture(captures, receipt_id=<exact SHA256 pin>)

Use a dedicated existing file-backed connection opened read_only=True, owned by
the reader for its transaction; no outer transaction. SQL and operational errors
propagate. The CLI opens read-only itself. No initialization, migration, repair,
loading, source acquisition, publication or strategy execution occurs.

## Independent claims

- archived_integrity_verified: receipt hash, canonical replay, deterministic policy,
  request revision, duplicated metadata and aware UTC-equivalent clocks match.
- native_capture_provenance_verified: exact native contract/definition registries,
  each registry origin's OWN request scope, origin attempt/input link, and complete
  PLANNED -> RUNNING -> SUCCEEDED origin lifecycle verify. An unrelated successful
  job cannot impersonate the pinned receipt's first_job_id.
- reassessment_history_verified: all request-revision receipt nodes and links are
  resolved BEFORE any policy status or success selection. Writer @1 links every
  prior distinct receipt; this consumer requires that complete comparable DAG.
  Missing nodes, cycles, forks or omitted ancestor links require review.
- pinned_receipt_is_history_head: graph position only, never a current permission.
  An exact retry of an older receipt does not rewrite its links or revive it.
- archived_policy_status: historical ACCEPTED_RESEARCH_ONLY or REJECTED result,
  not a current response. Both receive identical integrity/provenance treatment.

The consumer also resolves ALL scoped jobs, including jobs without domain attempt
links after operational failure. It cross-checks linked attempts in the opposite
direction. Any unmatched, incomplete, failed, cancelled, malformed or unsupported
attempt requires history review. This intentionally conservative @1 policy retains
terminal failure obligations rather than treating successful retries as repair.
A verified original capture may coexist with later history review requirements.
The result preserves those separate flags rather than inventing a business rejection.

Current-request admissibility is NOT evaluated here. For a new explicit request,
call native assess_publication_use against the publication registry afresh; do not
turn this result, an old receipt or offline replay into an authorization token.
No combined current-use API or positive decision lane is introduced. All current,
authorization, decision-eligibility and replay-authenticity flags stay false.
Even a graph head is merely the last distinct stored assessment observed in this
snapshot, not proof of present source health, economic validity or availability.
Native provenance is application audit evidence under trusted database ownership,
not cryptographic authenticity or protection against privileged database rewriting.

## Bounds and clocks

One database transaction supplies the observed archival snapshot. All owned SQL
uses fully quoted current-catalog/schema/object names. Receipt bytes are SQL-gated
at 16 MiB, registry JSON at 32768 bytes, reason JSON at 16384 bytes, link JSON at
70000 bytes. Request history: <=1001 receipts, <=32 MiB total receipt bytes, <=2000
jobs/attempts and <=4 event rows per job (four means invalid lifecycle). Registry
origins may belong to other requests and are independently bounded and validated.
Limits require review, never partial all-clear. Timings are metadata only; aware
clocks compare as UTC instants and never use replace(tzinfo=UTC). No now() enters
reader identities, and no record clock is substituted for source evidence.

## CLI

    uv run python scripts/inspect/inspect_admission_capture.py --receipt-db <db> --receipt-id <pin>

Default is a no-I/O plan. Add --inspect for read-only verification. Exit 0 means
archived history verified (not policy acceptance), 2 means review required, 1 means
operational inspection failure with redacted diagnostics. No payload BLOB or frozen
source content appears in the CLI summary.

## Validation scope

Delivered tests use native capture, policy, AuditLedger and DuckDB from the local
repository, replacing only the upstream publication reader boundary. They are NOT
full native source-to-decision end-to-end tests. Native tests and mandatory local
QA have not been run in the delivery sandbox. Sandbox checks cover extracted pure
history/lifecycle helpers, AST syntax, no-I/O CLI planning, line lengths, ZIP CRC
and exact per-file checksums. No dependency stand-ins are shipped.

Still separate gates: actual local QA, current eligible publication contracts,
positive decision inputs, strategy/decision records, complete replay and platform
acceptance. No data loading or migration is authorized by this package.
