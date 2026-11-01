# Exact recorded underlying statement/current-support revalidation @1

## Source reconciliation

Latest USER-REPORTED baseline: dee3bc7, HEAD and origin/feat/medallion-feature-store,
QA/tests passed. Local repository is unavailable; branch/worktree/HEAD and committed
bytes are not independently verified. Unlike the previous retrieval gap, current
uploads now include underlying_assertion_reader.py, bronze_support_reader.py,
underlying_support_adapter.py and the explicit short pytest IDs in snapshot tests.
These actual interfaces and native fixtures were inspected. No older generated file
is substituted. All uploaded Windows-safe filename/SQL alias and short-ID fixes are
preserved. Existing writer/reader/schema/Layer/dependency files remain unchanged.
Python >=3.12 is respected; no forced downgrade from the reported local uv runtime.

## API

    revalidate_underlying_assertion_support(
        registry, bronze,
        assertion_id=<exact recorded assertion SHA256>,
        request=UnderlyingAssertionRequest(...),
        expected_audit=IngestAuditExpectation(...),
    ) -> UnderlyingSupportRevalidation

Version underlying-assertion-support-revalidation@1. Separate owned file-backed
read-only connections, including no shared/aliased attached file paths, and no
outer transactions. No writes, initialization, network, source loading or audit repair.
The independently supplied typed request must reproduce the exact assertion ID;
otherwise return review before database queries. No arbitrary encoded receipt import.

Supported dependencies:
- underlying-identity-assertion@1
- underlying-assertion-recording-consumer@1
- pinned-bronze-support-storage@1
- actual native typed request-to-support adapter

## Algorithm

1. Reconstruct/validate the explicit typed request and reviewed audit metadata.
2. Invoke the native archived consumer: full bounded recording history and audit
   obligations must verify, and the exact pin must be the last DISTINCT recorded
   statement for its scope. This is an evidence position, not current identity truth.
   Older pins stop before any Bronze checks; no old-good fallback after later
   disputes, withdrawals, unsupported or incomplete evidence.
3. Retrieve bounded exact assertion bytes with fully quoted catalog/schema/object
   SQL and require equality to the independently supplied native encoded request.
   Replay through the native codec for content consistency, never as authority.
4. Invoke the actual native supporting-storage adapter TWICE. Retain both results,
   including rejected/unsupported/review evidence. Never select a previously good
   observation after a later failed or changed one.
5. Reverify archived recording/history and exact statement bytes after the support
   observations. Compare full reader DTOs INCLUDING complete registry evidence
   fingerprints, not status or kind alone. Compare complete source DTOs/fingerprints
   with type-sensitive canonical JSON (not Python False == 0 equality).
6. Only complete, unchanged observations yield verified_recording_and_current_storage.
   Review outcomes retain before/after native evidence and obligations. SQL/source
   operational failures propagate, not fabricated identity/business rejections.

An exact successful registry retry changes the archived whole-registry fingerprint
and blocks this observation if it occurs between reads. A successful scoped Bronze
retry changes its observed source fingerprint. New source conflicts, later incomplete
jobs and changed registry evidence cannot be hidden by picking an earlier success.
A failed origin is not healed by later success. No rows/links are repaired or rewritten.

## Statement kinds and authority

All three native statement kinds (ASSERTED, DISPUTED, WITHDRAWN) can have internally
consistent archived recording AND present supporting storage. This result verifies
that relationship only. It is NOT acceptance of a claim, identity eligibility, a
binding, an authenticated revocation or authorization. An unverified withdrawal is
not treated as a privileged command; a newer ASSERTED statement is not automatically
a resolution of earlier disputes. The full underlying claim history still exists.
The combined service deliberately supplies NO positive identity/decision lane.

identity_verified, issuer_authenticated, canonical_underlying_id, artifact-to-event
semantics, retry-link coverage, full Bronze acquisition provenance, availability,
historical validity, decision eligibility and atomic-cross-database assertions remain
False/None. Expected audit command/scope/config pins are caller-reviewed constraints,
NOT a trusted issuer/connector policy or access-control credential.

The Bronze source reader's @1 profile is NOT widened: fresh all-new clean batches,
<=64 events, same-origin artifact, one committed batch per root origin job and full
bounded scoped lifecycles. Mixed/retry membership and reused origins still require
review. Same-scope jobs do not establish universal retry linkage. Exact bytes/audits
do not prove that a source artifact semantically supports an external identity.
No unknown publication/availability/economic clocks are inferred or substituted.

## Observation fields and concurrency

- current_support_checked: both native supporting-storage calls completed; it is
  NOT shorthand for verified identity or complete acquisition semantics.
- exact_recorded_request_matched: final pinned bytes still match the explicit request.
- registry_unchanged_observed: complete native archived before/after results and
  exact bytes match, including the complete returned registry evidence fingerprint.
- bronze_support_unchanged_observed: full source before/after DTOs match. Two equal
  REVIEW results can match observationally while still requiring review overall.
- recording_before/after and support_before/after: retained native evidence, not
  independent permits that override the top-level review outcome.
- evidence_fingerprint: deterministic hash of explicit request-byte hash, audit
  expectations and the four returned evidence DTOs on success. It is not a signature,
  persisted approval, authenticity token or complete strategy/code/config replay.

Reads occur sequentially across separate database transactions. Two matching source
observations bracketed by registry snapshots detect OBSERVED drift only. They do not
prove simultaneous availability, future stability or absence of transient/ABA changes.
No lock, atomic multi-database frontier or executable strategy admission barrier is
acquired. Current source checking is not historical as-recorded replay or as-of proof.
The result is an ephemeral inspection, not an audited stored verification decision.

## Bounds, CLI and platform safety

Native registry/source bounds remain in force, unchanged. Additional exact statement
retrieval is capped at 16 KiB, rejects duplicates/missing/oversized BLOBs, and never
salvages a prefix. No-I/O CLI plan performs no file probes, DB opens, directory
creation, execution imports, network or credentials.

    uv run python scripts/inspect/revalidate_underlying_support.py `
        --identity-db <existing-registry> --bronze-db <existing-bronze> `
        --assertion-id <exact-pin> --request-file <reviewed-request.json>

Add --revalidate for existing inputs opened read-only. Request file is a strict
<=32 KiB object with EXACT keys assertion_request and expected_audit. Nested fields
match the two native dataclasses. Unknown fields/authority overrides fail. Output
omits request JSON and payloads; exceptions are redacted. Exit 0 is observed recording/
storage consistency, including DISPUTED/WITHDRAWN, NOT identity acceptance. Exit 2 is
review/argument error; exit 1 UNDERLYING_SUPPORT_REVALIDATION_FAILED. No execute,
initialize, allow-unknown, latest/current selector, repair or force-success option.

## Verification scope and next gates

Sandbox tests exercise the actual additional SQL helper, file-alias guard, canonical
comparison and CLI plan over real DuckDB synthetic fixtures. Those bytes deliberately
are NOT valid native assertions; passing helper tests does not prove orchestrated
recording/provenance. Native tests reuse the ACTUAL inspected native_source fixture
from test_bronze_support_native.py and real local writer, codec, AuditLedger, recording
consumer and Bronze reader. Mutation spies call the actual services, not replacement
verified-result implementations. They are not full provider/issuer E2E and remain
unrun here. See QA_REPORT.md and mandatory local QA runner.

Next substantive gates remain source-specific parsing/acquisition semantics, trusted
namespace/issuer evidence, independently authorized identity/binding assessments and
separate eligible temporal/publication evidence. This package does not manufacture
that missing authority. No market/identity loading, migration, live acquisition,
publication, registry write, trading or cutover was performed or authorized. Passing
package QA is not full-platform acceptance; data-loading hold remains in effect.
