# Pinned supporting Bronze storage/audit evidence @1

## Source/interface reconciliation

Latest USER-REPORTED baseline a331f45, HEAD -> feat/medallion-feature-store, QA/tests
passed. Origin/push not shown. No local repository access; Git/worktree and actual
committed bytes remain unverified. Project inventory/exploration did not return the
new archived assertion reader, its documentation or short pytest-ID correction.
This is a retrieval/upload gap, NOT proof the local committed work is absent. That
newer work is NOT recreated, modified or overwritten, and this package does not
assume its uninspected interfaces. Existing Windows-safe aliases and short-ID fixes
must be preserved locally. No changes to dependencies, schema, Layer or Python >=3.12.

Inspected actual underlying_assertion.py/store.py and bronze.py/native Bronze docs.
Bronze retains first_batch_key/first_job_id, but append_batch can count exact retries
whose first links point to earlier batches; it does NOT persist a general ordered
membership list for each batch. Therefore generic batch fingerprints CANNOT honestly
be reconstructed from first links alone. This @1 implements an explicit narrower
profile instead of guessing, filtering away conflicts or fabricating membership.

## APIs

    inspect_bronze_support(
        bronze,
        support=BronzeSupportPin(capture_event_id, envelope_hash, payload_hash,
                               byte_start, byte_end, fragment_sha256),
        expected_audit=IngestAuditExpectation(command_name, scope_ref, config_hash),
    ) -> BronzeSupportEvidence

    inspect_underlying_support_storage(
        bronze, request=UnderlyingAssertionRequest(...), expected_audit=...,
    ) -> BronzeSupportEvidence

Read-only file-backed owned Bronze connection, no outer transaction. Input types and
bounds are checked before DB inspection. One Bronze transaction covers the observed
payload, full supported batch, original artifact and scoped audit history. No DB/file
initialization, acquisition, external path/network access, identity recording or writes.

The adapter projects only the inspected typed assertion request's supporting pins.
It DOES NOT verify that the request was recorded, that its statement is last/current,
that its registry audit succeeded or that a newer dispute/withdrawal is absent. It
cannot bypass archived assertion consumption. No composed current-identity API is
introduced until actual latest consumer sources/interfaces are reconciled. No old
assertion/receipt is selected or revived by these independent source-byte checks.

## Supported evidence profile

1. Require Bronze schema 1 and native audit schema 1 in a dedicated Bronze/audit DB.
2. Require one exact variant under the target receipt ID; a later conflict blocks.
3. Verify exact payload/envelope hashes, canonical complete envelope, recomputed
   source/session/record receipt identity, field links, original receipt and optional
   exchange clocks as aware UTC-equivalent instants. Original recorded_at is separate.
   Validate exact original-payload byte interval/fragment hash; never decode or infer
   character/PDF/page boundaries. Origin kind is retained as DECLARED provenance.
4. Require a fresh conflict-free all-new batch: inserted_variants=input_events,
   exact_retries=0, conflict_variants=0. Read ALL first-linked members, require every
   member's current receipt to be nonconflicting, and verify each envelope/payload.
   Ingest sequence must be positive and unique; gaps are permitted, not repaired.
5. In this single-owner fresh-only profile, sequence order reconstructs insertion
   order. Recompute the exact native batch fingerprint from retained input_file_hash
   plus ordered receipt/envelope pins; compare original batch last_sequence to its
   members' maximum (NOT today's global cursor). Require one committed batch for
   the origin job. Multi-batch origin jobs require review under this @1.
6. Verify exact retained input-artifact bytes and hash; artifact first_job_id must
   equal batch/event origin job. A reused artifact from another origin requires
   review, not a claim that old artifact provenance is inherited automatically.
7. Verify origin job metadata against the caller's EXPLICIT reviewed command/scope/
   config pins. Root jobs only under @1 (non-NULL parent requires review). Read ALL
   jobs with the expected scope, plus the origin job regardless of its stored scope,
   BEFORE lifecycle success selection. Any metadata mismatch or nonterminal/failed/
   cancelled job requires review. Full bounded indexed lifecycle events, not latest
   SUCCEEDED alone. Support foundation's direct 3-state and staged 6-state success
   paths; no success-after-failure or published cancellation shortcut.

A later successful retry cannot heal an incomplete original ingestion job. Known
terminal failures remain obligations. Current receipt conflicts block every pinned
variant; no first/last or old-good selection. Unsupported mixed/retry batches or
artifact origins return review_required, NOT corrupt/rejected provider identity.
SQL/operational failures propagate in APIs; validation/coverage failures return
review-required evidence. No repair, adoption, truncation or forced success.

## What the result does and DOES NOT prove

Positive status verified_storage_evidence means internal native table/byte/batch
consistency and complete successful jobs UNDER THE SUPPLIED EXACT SCOPE/EXPECTATIONS
for this supported profile. Flags distinguish payload integrity, retained artifact,
fresh batch membership, original ingest audit and scoped audit history. A valid
origin can coexist with later scoped obligations and overall review_required.

Expected audit pins are caller-reviewed constraints, NOT an authenticated policy
registry. The caller can choose a fictional command/identity if a privileged writer
also forged matching database rows. Matching command/scope/config is not permission,
connector authorization, source truth, genuine provider receipt, external signature,
issuer authentication, or semantic support for a namespace/identifier.

BronzeEventStore trusts parsing/batch construction. Even a hash-correct artifact and
batch do NOT prove the input artifact actually parses to those events. Therefore
artifact_to_event_semantics_verified=False ALWAYS. Source-specific independent
parsing and acquisition protocol verification remain required. No payload is promoted
into canonical underlying identity and no claimed issuer is authenticated here.

Bronze does not retain a universal retry-attempt link table. Same-scope job observation
is NOT proof that every possible retry used that scope or that each sibling job
refers to this exact event/batch. retry_link_coverage_verified=False ALWAYS. No global
audit/other-scope all-clear is claimed. Acquisition authenticity, identity, issuer,
availability, historical-validity and decision-eligibility flags remain false.
No clock here becomes provider publication, information availability or economic time.

This package advances CURRENT SUPPORTING STORAGE verification, not canonical identity
or full source authenticity. Retained input bytes are reviewed as evidence only.
The snapshot fingerprint includes pins, expectations, target/member rows, original
artifact, batch and complete observed scoped jobs/events. Exact successful scoped
retries change it. Bytes contribute hash/length, clocks normalize to UTC. It is not
a signature, full DB/WAL/DDL hash, multi-resource snapshot or future-stability proof.

## Bounds and unsupported shapes

Target/member payload <=1 MiB each; <=64 fresh batch events, <=8 MiB aggregate batch
payload; retained input artifact <=16 MiB; envelope <=64 KiB; other projected strings
<=4096 UTF8 bytes, <=1000 scoped jobs, <=6000 lifecycle events (<=6 per job). Ingest
metadata expectations have command <=128, scope <=512, exact SHA256 config; required
root-job IDs <=128. Unknown extra namespaces block; this is not a full DDL/contract-
registry/permission audit. Original input artifact schema/decoder is NOT inferred.

Preflight count/payload checks and SQL CASE projection guards bound materialization.
Oversized strings are not silently accepted as NULL. These are evidence bounds, not
hard wall-clock or engine peak-memory guarantees. No capacity-based scope narrowing,
partial member salvage or reconstructed mixed-batch provenance.

## CLI

    uv run python scripts/inspect/inspect_bronze_support.py `
        --bronze-db <existing-db> --request-file <reviewed-request.json>

Default is a no-I/O plan: no execution imports, file probes, DB opens, directories,
network or credentials. Add --inspect for read-only observation. Request JSON is a
bounded <=8192-byte strict object with exact keys support and expected_audit, whose
fields match the two dataclasses above. No source/registry payload is printed, and
arbitrary exception text is redacted. Exit 0 means supported storage evidence,
NOT identity admission; exit 2 means review/argument error; exit 1 is redacted
BRONZE_SUPPORT_INSPECTION_FAILED. No --execute/initialize/network/repair/force option.

## Validation and next gates

Actual standalone reader tests run real DuckDB over synthetic rows; they are NOT
native ingestion, provider protocol or semantic identity E2E. Separate native tests
use actual local BronzeEventStore and AuditLedger, including the fully qualified
bronze catalog/schema correction, fresh batches, exact retries, conflict preservation,
mixed retry-batch refusal, artifact-origin reuse refusal and assertion-request adapter.
They remain unrun here. No native dependency stand-ins are shipped. Large values are
not embedded into parametrized IDs; quote-bearing aliases use Windows-safe filenames.
See QA_REPORT.md and mandatory local PowerShell runner.

Still required: reconcile latest archived-reader sources before integrated current-
assertion revalidation; source-specific acquisition/input-parsing provenance; trusted
namespace/issuer semantics; authoritative identity/binding decisions; temporal and
eligible-publication evidence. No actual market/identity loading, migration, live
acquisition, registry write, repair, strategy or decision-loop cutover was performed.
Package QA is not whole-platform acceptance; existing data-loading hold remains.
