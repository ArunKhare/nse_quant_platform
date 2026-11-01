# Whole capture-database evidence frontier @1

## Reconciliation

Latest USER-REPORTED baseline: b175e2c on feat/medallion-feature-store and origin,
QA/tests passed. Local Git/repository access was unavailable, so this is not
independently verified. Actual uploaded revalidation.py, its tests/documentation,
capture.py, archived reader and audit.py were inspected before implementation.
Uploaded revalidation uses captured-publication-request-revalidation@1 and its
DTO/receipt fingerprint deliberately does not include every audit row. Successful
exact retries may leave the archived DTO unchanged. This package closes that
observed capture-database drift gap without replacing the committed @1 service.
Existing SQL qualification corrections and Python >=3.12/dependencies are untouched.

## APIs

    observe_admission_frontier(captures) -> AdmissionFrontier

    revalidate_with_capture_frontier(
        publications, captures,
        receipt_id=<exact pin>, publication_id=<exact pin>,
        request=AdmissionRequest(...),
    ) -> FrontierRevalidation

Connections must be owned, file-backed and opened read_only=True, with no enclosing
transaction. The scanner's inventory/schema/row observation uses one capture-DB
transaction. The wrapper calls scanner -> committed native revalidation -> scanner.
It requires both native input/request checking AND equal before/after capture DB
fingerprints for a matched_research_input top-level result. Matching native rejection
remains rejection. Native review requirements never become all-clear.

The wrapper is additive, a separate explicit API. Existing revalidation remains @1
with its documented DTO-only observation semantics. Use the wrapper when this
stricter capture-frontier observation is required. No dispatch/cutover is automatic.

## Coverage and why whole database

Version: admission-capture-database-frontier@1. Coverage intentionally includes ALL
rows in all nine owned native tables, not only the pinned request:
- decision_inputs.admission_schema_versions
- decision_inputs.admission_contracts
- decision_inputs.admission_definitions
- decision_inputs.admission_receipts
- decision_inputs.admission_attempts
- medallion_audit.schema_versions
- medallion_audit.dataset_contracts
- medallion_audit.jobs
- medallion_audit.job_events

Every contract/definition origin is covered even if it belongs to another request.
No accepted/rejected, command, scope, terminal-state or success filtering occurs.
Unlinked jobs/events, exact retries and failed/pending evidence are included. This
avoids making an incomplete hand-selected dependency closure look authoritative.
It is intentionally overinclusive: activity on an unrelated request changes the
frontier and conservatively makes guarded revalidation require review.

Exact table inventory, ordered columns, SQL types and nullability are included.
Unknown tables/views, extra/missing columns, unsupported SQL scalar types and bounds
fail closed as FrontierReviewRequired. The scanner fingerprints schema-version ROWS
but does not interpret those versions as supported provenance; native verification
still validates the schema/contract/policy meaning. Fingerprinting is not validation.

All scalar row values are included. Exact receipt BLOB bytes are SHA256-hashed inside
DuckDB, with actual BLOB lengths included, rather than materialized/printed in Python.
Other columns (including receipt_byte_count) remain separate original values.
Canonical rows are sorted independently of physical insertion order; duplicate
multiplicity remains visible. TIMESTAMPTZ values normalize via astimezone(UTC).
Catalog names and file paths are excluded from identity, enabling relocation without
pretending physical file identity or origin authenticity. Fully quoted three-part
SQL handles catalog/schema collisions and embedded quotes.

This is a logical table-row observation, NOT a hash of DuckDB file pages, WAL,
constraints/indexes, sequences, permissions, application source, external files or
publication-registry contents. Column metadata is included; full DDL is not.
No raw/frozen inputs or arbitrary exception text are emitted by the CLI.

## Bounds

- 1001 receipt rows for the entire dedicated DB.
- 2000 rows per other table, except 6000 job_events.
- VARCHAR cell <=131072 UTF8 bytes; aggregate VARCHAR input <=8 MiB.
- BLOB cell <=16 MiB; aggregate BLOB bytes hashed <=128 MiB.
- Final canonical fingerprint document <=8 MiB.

Preflight aggregate byte/row checks precede payload projection. BLOB bytes never
cross the Python boundary. These bounds limit returned/materialized evidence, not
hard wall-clock execution or all internal database-engine work/peak memory. Canonical
encoding may expand text before the final document limit check. A capacity failure
returns no partial fingerprint. Do not increase limits merely to hide QA failures.

Whole-DB capacity is intentionally conservative. A future scoped dependency closure
requires explicit versioning and tests; this @1 does not silently filter history to
fit. A larger active DB may require review even when one request is small.

## Guard semantics and remaining uncertainty

A changed fingerprint returns top-level review_required with
CAPTURE_DATABASE_FRONTIER_CHANGED, even if nested native_result matched/rejected.
The nested result is retained evidence, not the top-level outcome or an independent
permission. Coverage failure returns review_required, not a policy REJECTED receipt.
Source/SQL failures propagate through APIs; the CLI redacts operational diagnostics.
No arbitrary external receipt import, repair, rewriting history or forced success.

Unchanged capture_frontier_unchanged_observed is agreement between two full bounded
capture-DB observations. It is NOT a guarantee of no transient changes between
observations, future stability, cryptographic authenticity, atomicity across the
capture and publication DBs, a strategy-input lock or simultaneous information
availability. The publication side still uses committed native revalidation, not
an entire publication-registry fingerprint. There is no atomic barrier or ACL.

All authenticity/authorization/decision-eligibility/atomic-cross-database flags stay
false. The scanner always has provenance_verified=False: native audit/source
verification remains necessary. An empty or consistently corrupted database is not
made valid by a stable fingerprint. Unknown availability/economic clocks stay unknown.

## CLI

    uv run python scripts/inspect/observe_admission_frontier.py --receipt-db <capture-db>

Default: no-I/O plan, no execution imports, path probes, files, network or credentials.
Add --observe for an existing DB read-only snapshot and summary. Exit 0 means
OBSERVED_NOT_AUTHORIZED, not healthy or admitted. Exit 2 means coverage/shape review
(or invalid CLI arguments); exit 1 is redacted ADMISSION_FRONTIER_FAILED.
Guarded request revalidation is provided by the Python API above, not this CLI.

## Tests / acceptance

Scanner tests run the actual scanner and real DuckDB over synthetic native-shaped
SQL fixtures, including nullable/default rows that are NOT valid captured receipts.
They deliberately do not claim native capture/provenance or E2E verification.
No dependency replicas or substitute audit/reader implementations are shipped.
Separate native tests invoke real capture/policy/archive/revalidation against local
repository dependencies, substituting only the publication-reader boundary. Those
must run locally and are not full source-to-decision E2E either. See QA_REPORT.md.

Remaining gates include positive eligible identity/temporal/publication evidence,
strategy inputs/decisions, durable complete replay and platform acceptance. This
package performs no loading, migration, acquisition, publication, repair or trading.
