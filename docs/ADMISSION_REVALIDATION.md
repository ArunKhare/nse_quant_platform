# Pinned captured-publication request revalidation @1

## Reconciliation / scope

Latest USER-REPORTED baseline: 5092b2f on feat/medallion-feature-store and origin,
with 2eab47e preceding it; user reports tests/QA passed. Not independently verified.
Uploaded admission_capture_reader.py is publication-admission-capture-consumer@1.
Uploaded tests include the fixed corruption SQL using fully quoted three-part
identifiers. No existing capture, reader, policy, test or dependency is replaced.
The current uploaded policy is research-publication-admission@1. Its accepted
research result is not authorization, and research-only point-in-time requests
always reject. This package does not create the missing positive decision lane.
Python >=3.12 remains unchanged; no forced runtime pin or dependency reduction.

## API

    revalidate_captured_publication_use(
        publications, captures,
        receipt_id=<explicit captured receipt SHA256>,
        publication_id=<explicit publication SHA256>,
        request=AdmissionRequest(...),
    ) -> AdmissionRevalidation

Separate owned file-backed connections, opened read_only=True; no outer transaction.
No receipt import, writes, initialization, acquisition, migration, repair or trading.
Input paths/aliases and attached database overlap are rejected using native checks.
No current/latest selector. Explicit pin and exact request are mandatory.

The implementation composes the existing native archive verifier and policy service.
It uses the inspected @1 reader's _record helper for bounded metadata-checked exact
receipt retrieval, and native canonical codecs. This is an explicit source-interface
dependency; reconcile changes rather than silently substituting a reconstructed
reader. Existing reader and codec byte/row/event bounds remain in force.

## Algorithm and refusal rules

1. Verify archived integrity, audited provenance and FULL reassessment history.
   Require the explicit pin itself to be the graph head. Do not find an old accepted
   receipt, filter rejected history, or select another pin automatically.
2. Read/replay the bounded captured receipt. Require its exact publication and
   UTC-normalized request to equal the independently supplied explicit request.
3. Freshly invoke assess_publication_use twice. Both invoke the native publication
   verifier. Compare exact encoded receipt bytes, not status or outer hash alone.
4. Reverify archive/history and captured receipt bytes after those assessments.
   A changed visible archival result, new head, unresolved attempt, or changed
   captured bytes requires review. Observed fresh assessment drift requires review.
5. Require fresh bytes to equal the captured receipt exactly. A changed source,
   audit fingerprint or request cannot silently become a new approved capture.
   If fresh input differs, report review_required with fresh receipt ID/status;
   capture an assessment separately through the existing audited writer only after
   explicit intent. The revalidator never writes that assessment itself.
6. An exact matching rejection returns rejected with native policy reasons.
   Exact matching accepted archival research returns matched_research_input.
   Neither return is an access credential, durable approval or decision permit.

An older accepted pin remains blocked after a newer rejected receipt, even after an
exact retry of the old accepted bytes. A rejected head that would now freshly accept
still differs in exact input; it requires explicit new capture/reassessment, not
replay-based revival or automatic authorization. Failed/incomplete attempts remain
review obligations under the committed archive consumer's conservative policy.
Source/SQL/operational failures propagate. They do not fabricate a rejected receipt.

## Meaning of result fields

- archived_capture_verified: the requested archived head was verified for this
  operation; it is not source authenticity or an ACL check.
- current_request_checked: fresh native publication/request policy assessment ran.
  This is not a live Gold/provider check or proof of source-current market data.
- observed_inputs_match: exact bytes of the stable fresh assessment and captured
  receipt matched in these observations.
- research_policy_satisfied: only an exact matching accepted archival research
  input under @1; not research_analysis_authorized.
- fresh_receipt_id / fresh_policy_status: summary of a stable observed assessment,
  not a persisted new capture. Review on drift may omit these fields.
- evidence_fingerprint: deterministic hash of returned before/after archive DTOs
  and captured/fresh receipt hashes. It is NOT the complete audit-row history,
  cryptographic authenticity, a signature, a token or complete strategy replay.

All authorization, decision-eligibility, availability, economic-validity,
source-current and replay-authenticity flags stay false. No clock is inferred.
Knowledge cutoff/economic instant remain independent explicit axes. UTC-equivalent
requests compare equally. Request/record/audit clocks are not source availability.

## Concurrency / limits

Two independent databases are not one atomic information frontier. Two agreeing
fresh observations and before/after archive DTOs detect observed drift only. The
archive DTO does not fingerprint every audit row: an exact successful retry may
leave it unchanged, and transient changes between observations may go unobserved.
This package therefore never claims a frozen audit frontier, simultaneous snapshot,
future stability or atomic cross-database barrier. No lock or publication authority
is acquired. Keep trusted database ownership and appropriate operational isolation.
Do not use this read-only result as an executable strategy admission permit.

## CLI

    uv run python scripts/inspect/revalidate_admission_capture.py `
        --publication-db <registry> --receipt-db <captures> `
        --publication-id <pin> --receipt-id <pin> `
        --use-case ARCHIVED_RESEARCH_ANALYSIS

Default is a no-I/O plan: no DB imports/opens, path probes, directory creation,
credentials or network. Add --revalidate to open both existing inputs read-only.
POINT_IN_TIME_DECISION also requires --knowledge-cutoff and --economic-at with
aware ISO8601 values. It remains rejected by research-only @1 for matching input.
Exit 0: plan or matched research input, NOT authorization. Exit 2: review/rejection
or argument error. Exit 1: redacted operational failure. No full source DTO/BLOB or
arbitrary exception text is printed. There is no --execute/initialize/force option.

## Acceptance and validation

Native tests cover exact research matches, matching point-in-time rejection,
UTC-equivalent axes, request/publication mismatch, fresh evidence drift, no old-good
fallback, rejected-to-accepted drift, failed scoped jobs, source errors, capture
history changes during assessment, read-only inputs and no-I/O CLI planning.
They substitute the upstream publication-reader boundary, not the native policy,
capture store, audit service or archived consumer. They are NOT full native E2E.
Native tests and mandatory repository QA must run locally; see QA_REPORT.md.
No skipped tests, weakened assertions, type ignores, dependency stand-ins or runtime
fallbacks are introduced. Passing package QA is not whole-platform acceptance.
Still required: positive eligible identity/temporal/publication contracts, executable
strategy/decision input gates, audited decisions, full replay, platform acceptance.
No data loading, migration or decision-loop cutover is authorized.
