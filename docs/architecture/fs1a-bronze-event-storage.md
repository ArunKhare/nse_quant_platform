# FS1a: append-only Bronze event storage and audited JSONL import

Status: additive storage implementation. Not live collector integration or complete
production acceptance. Requires the QA-passed A1 audit and A2 manifest foundation.

## Purpose

Preserve the earliest retained provider representation as bytes and distinguish it
from later IV/Greeks or normalized observations. No existing option_stream rows are
renamed Bronze, and no legacy table, source DB, backfill or strategy is changed.

## Storage model

Use a dedicated single-owner DuckDB database. Explicit initialize() creates:
- bronze.schema_versions (version 1)
- bronze.event_variants
- bronze.input_artifacts
- bronze.ingest_batches
- bronze.ingest_sequence

The API exposes initialize, target verification, append_batch and conflict inspection.
There is no update/delete/replace method. Direct SQL privileges are not restricted by
this API; it is not a tamper-proof/WORM store. Administrative access, backups and
retention must be governed separately. Reject user tables outside Bronze/audit schema
before initialization; do not point the importer at the operational legacy database.

The caller owns connection and transactions outside each append. One store owner
only: the instance lock does not coordinate different instances/processes. No nested
outer transaction, distributed lease, fencing or multi-writer support is implied.

## Identity

capture_event_id = SHA256(canonical [source, capture_session_id, source_record_id]).
source_record_id identifies one receipt at the earliest retained capture boundary.
A retry preserves its original ID and metadata. New receipts get new IDs even when
payloads are identical. Provider event identity is a separate optional field.
Do not use only timestamp/token/payload hash as a capture receipt identity.

Each immutable variant has envelope_hash, payload_hash, exact payload BLOB,
received_at, actual recorded_at, optional exchange_ts and lineage to first batch/job.
Envelope includes format, origin and optional provider/instrument metadata. Timestamps
canonicalize to aware UTC for hashing; missing exchange time is not fabricated.

Same capture identity + same envelope => exact retry, no new variant.
Same capture identity + changed bytes OR metadata => append another variant, preserve
both, and flag the identity as conflicting. Existing records are never rewritten.
All variants under a conflicting identity require review; never automatically select
first/last as canonical. Silver must implement an availability-aware resolution policy.

The ingest_sequence is a single-owner ingestion cursor, NOT a feature publication
sequence or exchange sequence. Rollback can leave gaps. Do not assume it provides
multi-process commit ordering. recorded_at is set by storage, not backdated to market time.

## Input artifacts and atomic batches

Preserve the exact bounded input artifact BLOB with SHA-256. The JSONL importer
passes the exact bytes read, including whitespace. Batch fingerprint includes artifact
hash and ordered event identities/revisions. Reusing a batch key with different input
fails even if the change was merely whitespace. Choose stable batch keys deliberately.

One transaction appends the artifact, event variants and ingest batch receipt.
Failure rolls all these back. Exact committed batch retry creates no new domain rows
and returns already_committed=True. Each audited CLI attempt still has a distinct job.
The original receipt retains the job that first committed it; later retry jobs link
through manifests to the same batch fingerprint.

Default hard limits: 16 MiB input artifact, 10,000 envelopes, 1 MiB individual payload.
The storage API expects trusted parsing/batch construction; it does not prove a
caller-supplied payload was actually received from a named provider.

## Representation and provenance

payload_format must say what bytes are retained: e.g. provider_binary or
 decoded_provider_json. Canonical JSON produced after decoding is not original wire
capture. Preserve that distinction. origin_kind must be live_provider,
historical_import or legacy_snapshot. This is declared provenance, not provider
attestation. Never mark old computed option_stream rows as first-hand raw events.

If a legacy observation lacks original receipt time, do not invent one in the past.
Record import receipt time and legacy origin; carry historical market time separately
only where known. Native live integration must assign receipt IDs and receipt time
before enrichment, and preserve them through queue retries.

## Import envelope (one object per UTF-8 line)

Required fields:
- envelope_version: integer 1
- source, capture_session_id, source_record_id: string identities
- received_at: timezone-aware ISO timestamp
- payload_base64: exact retained payload bytes in strict base64
- payload_format: declared representation
- origin_kind: explicit provenance category

Optional: exchange_ts, provider_event_id, instrument_ref.
Unknown fields/versions and malformed values are rejected. JSON data is not flattened
into contract analytics. No quote validation or IV computation belongs in this importer.

## CLI planning and execution

    uv run python scripts/ingest/import_bronze_events.py --input events.jsonl --bronze-db data/bronze/capture.duckdb --manifest-root data/bronze/manifests --batch-key SESSION_BATCH

Default planning reads/validates bounded input but creates no DB, schema, directory or
audit records. --initialize alone still does not execute. To create a dedicated new DB,
add --execute --initialize --code-revision YOUR_COMMIT after review and local tests.
Subsequent imports can omit --initialize. No broker connection or secrets are loaded.

Execution verifies target, optionally initializes Bronze, initializes A1 audit,
registers the dataset contract, records a plan, and performs audited append. The domain
receipt is committed with its events. External audit finalization/manifests are not
atomic with that domain transaction: a committed batch may precede an audit failure.
Inspect ingest_batches and retry with the SAME immutable batch before deciding recovery.
No transactional outbox/recovery reconciler is implemented yet.

Status COMMITTED_WITH_CONFLICTS means evidence was preserved but needs review; CLI
exit 0 indicates successful storage, not trading/research eligibility. Consumers must
not interpret it as clean input. Conflicting IDs in the summary are scoped to this import.
All conflicting identities remain inspectable from the store.

## Integration gates

Before wiring the live collector:
1. Capture callback ownership and ID allocation must be reviewed at the actual earliest
   retained provider boundary, not at an already-enriched chain snapshot.
2. Add bounded durable queue/checkpoint, backpressure, reconnection and crash recovery.
3. Specify what happens when capture persistence fails; never silently drop and continue.
4. Verify no raw-store update methods are reachable from backfills/features.
5. Establish host clock quality, volume/storage budget, retention and restore procedures.
6. Validate payload checksums/integrity and corrupted-storage detection operationally.
7. Add replay/as-known-at conflict resolution in Silver, not in raw capture storage.

Legacy source-protection fixes remain urgent; this additive store does not make old
backfill commands safe when run directly against the legacy DB.

## Validation

21 tests executed here with real disposable DuckDB databases and no ledger stubs in
storage/parser tests. Covered exact bytes/artifact preservation, retries, conflicts,
receipt vs tick identity, timezone hashing, type/limit checks, failure rollback,
legacy-target rejection, schema version handling, parser rejection and read-only plan.
One integration case against installed A1/A2 is supplied for local execution, not run here.

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

No production claim until actual audit integration, process-crash/disk-full/restart,
Windows ownership behavior, backup restore, integrity and sustained-load tests pass.

## Commit title after local QA

feat(data-platform): preserve Bronze event bytes and capture identities
