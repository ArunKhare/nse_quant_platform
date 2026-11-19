# Verified archived underlying assertion recording @1

## Reconciliation

Latest USER-REPORTED baseline: 57ad6ed (HEAD -> feat/medallion-feature-store), with
QA/tests passed. The latest Git line does NOT establish an origin decoration/push.
Local repository access is unavailable; branch/HEAD/committed bytes remain unverified.
Inspected actual uploaded underlying_assertion.py, underlying_assertion_store.py,
its tests/documentation and native AuditLedger. Store underlying-assertion-store@1,
assertion underlying-identity-assertion@1, schema 1. Existing corrected quoted SQL,
Windows-safe alias fixtures, immutable bytes, false authority flags and all-prior
prior_assertion_ids_json semantics are preserved. Additive files only, no schema,
Layer enum, dependency, Python >=3.12 requirement or writer changes.

## API and exact claims

    read_underlying_assertion_recording(
        registry, assertion_id=<exact SHA256 statement pin>,
    ) -> UnderlyingAssertionRecording

Use an owned existing file-backed connection opened read_only=True; no outer
transaction. This is ARCHIVED registry consumption only: no Bronze input/path lookup,
network, issuer check, current-support verification, writes, repair or initialization.
It distinguishes:
- archived_integrity_verified: exact statement codec, deterministic identity, scope,
  stored kind/version/length and aware original record clock match.
- native_recording_provenance_verified: native contract and definition origins are
  successful in their OWN subject scopes, and the pinned statement's own original
  job/attempt has a full successful recording lifecycle and exact scope/config.
- registry_history_verified: all bounded registry statements and all subject graphs,
  jobs, attempts and lifecycle events are covered and internally consistent, with
  no unresolved recording audit obligations.
- pinned_is_last_distinct_statement / last_distinct_statement_id: evidence ordering
  within that exact subject scope, NOT canonical status, acceptance, active identity,
  authenticated withdrawal, authorization or permission to use the statement.

ASSERTED, DISPUTED and WITHDRAWN receive identical recording-integrity treatment.
A verified archived recording can contain a false statement or an unauthenticated
withdrawal. No status is silently promoted into identity verification. All canonical
ID/authentication/availability/historical-validity/decision flags stay None/False.
current_bronze_support_checked and bronze_acquisition_provenance_verified stay False.
No self-hashed/offline statement is sufficient without the native registry/audits.
Even complete application recording evidence is NOT cryptographic authenticity or a
database permission boundary against privileged rewriting.

## Full conservative snapshot and order of resolution

One registry transaction reads all nine native domain/audit tables, including
other subject scopes, contract/definition origin scopes, unlinked jobs and failed/
pending evidence. No assertion-kind, successful-job or current/latest WHERE filter.
Explicit table/column inventory and scalar types are checked; unknown objects or
extra/missing columns require review rather than silent interpretation/repair.

Every statement is decoded; every scope's all-prior links must form a complete
comparable acyclic evidence history. Missing links/nodes, forks, cycles, duplicates
and cross-scope edges block. These links never erase statements or imply authorized
supersession. An old ASSERTED exact retry after a WITHDRAWN record leaves its prior
links unchanged and cannot change the last distinct statement. No old-good fallback.

All job metadata and full event sequences are examined. Success is exactly
PLANNED -> RUNNING -> SUCCEEDED, indexes 1..3, aware clocks and no success reason.
Valid pending or FAILED/CANCELLED sequences remain obligations, not success. An
incomplete origin cannot be healed by successful retry. Registry origins may be
from other scopes: their own linked statement scope/config is validated, not the
requested target's scope. Attempts are checked against jobs and exact statement
scope; successful jobs without attempt links and attempts without jobs require
review. Orphan audit events/unsupported commands/configs also block.

The snapshot is intentionally whole-registry and conservative. A failure/incomplete
job on another scope can block registry_history_verified for this pin. This is not a
claim of global source health and does not require unrelated statement truth. It
avoids silently omitting cross-scope origins or unknown operational obligations.
Bounds/validation failures return review_required; SQL/operational failures propagate
through the API and become a redacted CLI error. No business rejection is fabricated.

## Fingerprint, clocks and bounds

A successful result hashes all selected native evidence rows, preserving duplicate
multiplicity, clocks, attempts and full event history. Statement BLOBs contribute
exact SHA256 and byte count after codec verification. Exact successful retries change
the fingerprint even when statement bytes/kind are unchanged. Rows are canonically
sorted, independent of physical row order; aware clocks normalize using
astimezone(UTC), never replace(tzinfo=UTC). No now() enters reader identities.

Fingerprint is a deterministic observed registry-evidence commitment, NOT a signature,
issuer trust assessment, full DDL/file/WAL hash, constraint/permission fingerprint,
Bronze provenance proof, atomic cross-database barrier or complete strategy replay.
It covers the one archival snapshot only; it does not assert future stability or
absence of transient changes around other operations. Review outcomes may omit it.

Limits: entire registry <=1001 statement rows; <=2000 rows per other table except
<=6000 job_events; assertion BLOB <=16 KiB; prior-link JSON <=70000 bytes; registry
JSON <=32768 bytes; other strings <=4096 bytes; aggregate selected string/BLOB
materialization <=8 MiB and final fingerprint document <=8 MiB. Read guards distinguish
oversized values from genuine NULLs before semantic processing. Limits require
review, not partial coverage or silently omitted history. These limits do not assert
8 MiB peak Python/engine memory or a hard query runtime; canonical encoding can expand
before its final size check. Whole-registry limits may block a small pin in a larger
DB; no dynamic scope narrowing to hide evidence is implemented.

## CLI

    uv run python scripts/inspect/inspect_underlying_assertion.py `
        --identity-db <existing-registry> --assertion-id <exact-pin>

Default is no-I/O planning: no path probes, DB opens/imports, directories, credentials
or network. Add --inspect to open the registry read-only. Output is a bounded summary,
not request JSON or support payloads. Exit 0 means verified ARCHIVED RECORDING, including
DISPUTED/WITHDRAWN, NOT identity truth/approval. Exit 2 means review/argument error;
exit 1 is redacted UNDERLYING_RECORDING_INSPECTION_FAILED. No source loading, execute,
initialize, repair, forced success or current/latest selector.

## Validation / further gates

Sandbox executes actual pure history/lifecycle and real-DuckDB snapshot tests over
synthetic SQL fixtures. Those fixtures are deliberately not valid recorded claims;
passing snapshot checks is not native recording/provenance verification. Separate
native writer/audit/reader tests reuse the ACTUAL existing registry fixture from
 test_underlying_assertion_store.py, without shipping replacement dependencies. This
explicit test dependency must be reconciled if the local fixture changed. Those tests
remain unrun in the sandbox and are not full Bronze/issuer/source-to-decision E2E.
See QA_REPORT.md and the mandatory local PowerShell runner.

Next substantive identity gates remain: trusted namespace/issuer/source semantics,
full supporting Bronze acquisition provenance and current support revalidation,
authoritative underlying identity decisions and explicit derivative bindings with
conflict/authorized-revocation semantics, separate temporal/publication evidence and
positive admission. No verified underlying identity or derivative binding is minted
here. No market/identity data loading, migration, acquisition, repair or cutover is
performed/authorized. Package QA is not whole-platform acceptance.
