# FS2c1: invalidation-first native reference consumption

## Scope and source baseline

User reported FS2b1/FS2b3 tests and QA passed and committed. Inspected actual Project
Files expose native_reference_silver.py, native_reference_evidence.py, native_reference_decode.py
and FS2b3 architecture/operations documents. FS2b3 records immutable assessments and
supersession edges but deliberately does not provide a publication/quality-filtered
read API. High-level legacy roadmap documents lag; they do not override this design.

This additive package implements a read-only evidence consumer for that native dataset.
It does not modify existing files, normalize more data, migrate schemas, publish bundles,
resolve canonical instrument identities or change any decision-loop/strategy/eligibility.
No compatibility wrapper for a legacy cache or the offline FS2b1 reader is introduced.
No broker request, credential lookup or persistent export writer.

## Version and interface

Resolver native-reference-consumer@1. Dataset input silver.kite_http_reference_results
schema 1, pinned by EXACT assessment revision ID. There is no implicit latest selection,
date-derived instrument snapshot selection or automatic decoder/version promotion.

lookup_native_reference(bronze, silver, assessment_revision_id=..., instrument_token=...)
returns a frozen NativeReferenceLookup: matched, ambiguous, unresolved or blocked,
a bounded reason code, active assessment IDs and exact row-reference pins. Row pins
contain assessment revision, zero-based CSV record ordinal and source_fields_hash.
They do NOT identify a globally stable financial contract or an underlying.

The CLI opens both source DBs read-only, does not create missing DBs or initialize
schemas, and prints reference identifiers/ordinals/hashes only. No output-file option.
Expected blocked/unresolved results are successful inspections (exit 0); infrastructure
or malformed invocation errors exit nonzero with sanitized diagnostic codes. Consumers
must inspect status/reason rather than treating exit 0 as usable/published data.

## Resolve invalidations BEFORE filtering quality

1. Pin exact assessment and obtain its input_revision_id.
2. In one Silver read transaction, read ALL assessments in that group without filtering
   classification, schema version or audit state. Read their supersedes_json edges.
3. Validate IDs, groups, duplicates, bounded link sets and references. Reject dangling
   edges, cycles and multiple active heads. Iterative topological traversal avoids
   recursive-stack failure on deep valid histories.
4. A superseded requested revision returns blocked without falling back or exposing
   any automatically chosen replacement's token mapping. Even a quarantined, unsupported
   or incompletely audited superseder blocks an earlier normalized value. Such rows
   are never discarded by a "WHERE classification='normalized'" prefilter.
5. Only the unique active exact pin proceeds to schema, identity, job and quality checks.

This is a conservative fail-closed reader of the existing FS2b3 supersession contract,
not an audit repair service. It neither edits edges nor manufactures job success.
Raw SQL tampering may cause denial of evidence consumption; application APIs are not
a permissions boundary against arbitrary DB-owner mutation.

## Positive binding requires fresh source verification

Validate the pinned input/revision hashes against the four Bronze pins and recorded
normalizer/content/CSV versions. Require the ORIGINAL normalization job's exact command,
scope/config fingerprint and latest SUCCEEDED state. A later successful retry does not
silently legitimize an earlier row whose first job remained failed/incomplete.

Use the inspected inspect_reference_pair API to recheck current native Bronze evidence,
including newly appended conflicts even if no new Silver assessment has been made.
Recompute normalized content with the exact currently supported versions; compare
canonical output, complete gate evidence, source clocks and both payload hashes to the
stored assessment. Source mismatch, unsupported version, missing artifacts, incomplete
audit or transport failure yields no binding. The current implementation deliberately
blocks unsupported archived versions instead of recomputing them with new code under
an old label. A future archived-decoder registry requires separate implementation.

Verify row ordinals/tokens/hash types before returning pins. One token row => matched;
multiple rows, even identical duplicates => ambiguous; absent token => unresolved.
No first/last-wins deduplication, provider-name underlying inference, expiry-derived
validity, symbol heuristic or stable token-to-contract identity.

## Bounds and snapshot limitations

Silver history <=1001 assessments, each <=1000 edges, links JSON <=100000 characters.
Gate JSON <=131072 characters, source clock JSON <=32768 characters. Encoded result
JSON returned from SQL <=128 MiB, normalized rows <=200000. At most 1000 token candidates;
excess fails closed without partial mapping. Bounds are explicit platform limits, not
market-feed performance or provider capacity assertions. SQL may still scan/allocate
internally; output bounds are not a measured peak-memory or latency guarantee.

Silver history and pinned row/job observations share one read transaction. Bronze
verification then uses the native verifier's SEPARATE read snapshot. This is NOT an
atomic cross-database lock or a guarantee against a conflict appended after inspection.
No persisted availability guarantee is created. Use one owner per DB and do not wrap
the APIs in external transactions or concurrent connection use.

## Availability, replay and next boundary

"Current" means current verification of the pinned receipt, NOT the latest provider
instrument list or current trading validity. Independent newer receipt groups do not
automatically supersede every older snapshot.

Output evidence_mode=PINNED_CURRENT_EVIDENCE_ONLY; canonical_contract_id is null;
historical_validity_asserted and publication_asserted are false. Current source
revalidation intentionally makes this inappropriate as an exact historical replay
selector: a later conflict can block data that was once considered valid. Research,
as_known_at and exact_decision_replay semantics must not be inferred from this API.

No caller-supplied publication date or synthetic past availability. Existing Silver
receipt/recording/publication/validity fields stay unchanged. No invalidation is hidden
by quality filtering and no older normalized row is resurrected after quarantine.

The next coherent package is an audited reference-bundle publication ledger with
explicit availability and revocation/supersession events. It must bind immutable code/
input versions and define safe read/commit boundaries and replay semantics. This
reader is a prerequisite, not an implementation of that publication contract.

## Validation limits

See VALIDATION.txt. Pure graph tests and SQL reader tests execute offline; the SQL
harness explicitly mocks native Bronze verification. Real A1/FS1a/FS2b2/FS2b3 pipeline
integration cases are separately supplied for local execution, not claimed run here.
No user Windows branch/HEAD, full QA, Python 3.14.2, load, live-feed, losslessness,
process-crash recovery or production readiness is certified.
