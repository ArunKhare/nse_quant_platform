# Persisted source-linked evidence_snapshots Silver

## Accepted baseline and additive scope

User-confirmed fc3f714 Bronze QA/tests are CLOSED, with matching reported HEAD/origin;
f239b89/5ffa108 decision-evidence Silver remains accepted and unchanged. These are supplied
short hashes, not independently inspected Git/worktree or full revision attestations.

This new family persists complete observations from ACTUAL evidence_snapshots native
Bronze. It does not rebuild decision_evidence, extend its naive-wall timestamp contract,
interpret plugin payloads, add Gold/admission/publication, replay original decisions or
release operational holds. No evidence-id mapping or join between the families is invented.

Store: legacy-evidence-snapshot-silver-recording@1.
Command: normalize.legacy_evidence_snapshots@1.
DatasetContract: silver.legacy_evidence_snapshots / 1 / APPEND_REVISIONS.

Only disposable synthetic fixtures are authorized. Real-data loading/migration,
production publication, identity/key/policy/authority registration, trading and cutover
remain HELD. Package QA is not platform acceptance or an operating release decision.

## Inspected source and representation contract

Actual current codec, Bronze producer/readers, SQL-seeded native tests and analogous
current decision-evidence Silver store were retrieved before implementation. The source
writer method was not retrieved or fabricated; native fixtures use the accepted actual
DuckDBStore schema plus EXPLICIT synthetic SQL, not alleged writer/plugin execution.

Source schema (unchanged) is exactly:

    run_id VARCHAR
    ts TIMESTAMP WITH TIME ZONE
    symbol VARCHAR
    plugin_name VARCHAR
    payload_json JSON

The source key is (run_id, ts, plugin_name). Symbol is NOT part of that key. Run/time/
plugin must be non-null; symbol and payload are nullable. Every retained row and ordinal
is included. Full accepted snapshot replay verifies key uniqueness even if a malformed
source had no physical constraints.

New materialized Silver columns retain run_id, ts, symbol, plugin_name and payload_json.
ts is genuine TIMESTAMPTZ. payload_json is deliberately nullable VARCHAR containing the
EXACT original source CAST(JSON AS VARCHAR) text, NOT another JSON parse/storage step.
This declared representation change avoids syntax revalidation, normalization, extraction
or loss of retained whitespace/duplicate keys. Complete context retains the original JSON
source schema. No claim is made that a pure content constructor attests a JSON SQL column;
actual native Bronze capture provides that separate source-type observation.

SQL NULL payload remains None; JSON literal null remains text "null". Nullable symbol
remains None and is distinct from an empty string. No available scalar exists or is added.
There is no Boolean conversion, payload availability reconciliation, JSON flags extraction
or payload interpretation. Outer context/snapshot/record JSON is separately strict.

The stored aware ts is normalized by the accepted UTC instant codec, not assigned UTC
to a naive timestamp. Native materialization roundtrips that exact instant through
codec.encode_cell. Source naive timestamps reject. Original timezone labels/spellings,
writer clocks and overwritten history are not recovered. This is not decision_evidence's
naive TIMESTAMP family: its accepted wall-field code remains untouched.

SQL source instant, native import receipt and native recording/audit clocks remain
separate. None establishes independently evidenced original availability, economic validity,
knowledge cutoff or authoritative market/plugin time. stored_ts_instant remains the
retained SQL instant only; original_availability_at and canonical identity remain null.
Original classification/limitations are retained byte-for-byte from the accepted codec:
RETAINED_LEGACY_EVIDENCE_SNAPSHOT_NOT_ADMISSION, false payload interpretation/JSON
revalidation, original provider/history recovery, native decision replay, verified
availability/economic validity, publication and decision eligibility.

## APIs and meaningful native path

src/nse_quant/data_platform/legacy_evidence_snapshot_silver_store.py:

- EvidenceSnapshotBronzePins(source_label, snapshot_id, capture_event_id, envelope_hash,
  recording_fingerprint)
- initialize_evidence_snapshot_silver(empty_dedicated_file)
- observe_evidence_snapshot_bronze(readonly_bronze, pins=...)
- persist_evidence_snapshot_silver(readonly_bronze, initialized_silver, pins=...,
  expected_context_sha256=..., actor_id=..., code_revision=...)
- read_evidence_snapshot_silver(readonly_silver, revision_id=...,
  expected_recording_fingerprint=...)
- revalidate_evidence_snapshot_silver(readonly_bronze, readonly_silver, revision_id=...,
  expected_recording_fingerprint=...)
- revalidate_evidence_snapshot_silver_source(readonly_legacy, readonly_bronze,
  readonly_silver, revision_id=..., expected_recording_fingerprint=...)

observe invokes the ACTUAL pinned public read_evidence_snapshot_bronze, the ACTUAL
original read_recording_bytes, reconciles the independently reviewed recording pin,
retains COMPLETE snapshot bytes in bounded context, derives records using the actual
codec, and repeats the public reader. The producer requires a separately reviewed
full-context hash and repeats the whole observation again before persistence. No caller-
successful DTO, raw source SQL or offline context is imported as native recording proof.

Pure _derive reconstructs content only, not independent native audit/source attestation.
Native production/current-source calls establish their separate original obligations.
Original code/dependencies are imported, not reconstructed replacements in the ZIP.

## Persistence, scope and audit

Actual native AuditLedger/DatasetContract are reused. Dedicated tables retain definition,
set/full context, every observation/full record/all five materialized fields, original
native event link and attempt. Natural key uniqueness is also enforced per revision in
SQL as UNIQUE(revision_id,run_id,ts,plugin_name), independent of nullable symbol.

Scope binds profile version plus native capture_event_id only. Labels, snapshot/envelope/
recording/context review pins, runtime and actor/revision labels cannot heal the SAME
failed event obligation. A different actual native event is another subject, not proof
of authenticated namespace authority or recovery of an old failed job.

Any existing set/attempt/scoped job or orphan observation for the event blocks BEFORE
source reads. Two complete source observations must match. Set, every row and original
attempt commit atomically; domain failure rolls them back but leaves the failed audit.
Final SUCCEEDED is separate: committed content without original success is unreadable
and cannot be adopted. Successful retry, cleanup, supersession and recovery are absent.

Retained replay rechecks original definition/contract/dependency versions, exact materialized
types and nullability, full snapshot/projected bytes, all scalar/index values, revision/
scope, original job/config/scope and three-phase audit, link coverage and clocks. Same-event
rows under other revisions are included, so a good subset cannot hide orphan coverage.
A separately reviewed recording fingerprint binds full selected scalars/clocks/audit links
in addition to revision/content identity. Session timezone changes preserve UTC instant
fingerprint equality. Application integrity is not DB permissions or an authenticated root
against rewriting storage and supplying new trusted pins.

## Three distinct read levels

1. Retained Silver: complete original Silver recording/content/audit replay, no current
   native Bronze or legacy SQL claim.
2. Current Bronze: two actual complete native Bronze observations compared with frozen
   context, bracketed by pinned Silver reads.
3. Current legacy SQL: actual accepted whole-table legacy revalidation plus repeated
   native Bronze/Silver verification.

Changed current legacy SQL need not invalidate unchanged retained native evidence.
Missing current original Bronze audit blocks levels 2/3 while retained Silver can replay.
Operational/SQL errors propagate; they never become accepted/unavailable business outcomes.
Repeated observations are not an atomic cross-resource snapshot, independent time proof,
source-file hash or original plugin/strategy/decision replay.

Caller owns connections; no outer transactions/shared writers. Explicit initialization
requires an empty dedicated file; partial initialization is not adopted and readers never
initialize. Writers close before readonly reopen. Public readers enforce actual readonly
mode. Accepted same-file cursor separation rejects aliases while preserving parent owners.
All new domain mutations/assertions quote actual catalog.schema.table identifiers, with
real silver.duckdb/silver-schema collision fixtures, not renamed ambiguity avoidance.

## Independent bounds

All existing Bronze/source/other family limits remain unchanged.

- 1..1000 complete rows; no prefix/window/partial selection or paging.
- Original source snapshot <=1048576 bytes and source text/JSON <=65536 UTF-8 bytes/cell.
- Full wrapper context <=2200000 bytes, before strict parsing and hex decoding.
- Exact projected record <=524288 bytes each and <=4194304 aggregate.
- Materialized text <=65536 bytes/cell and <=1048576 aggregate, including nullable fields.
- SQL count/max/aggregate row-record AND scalar-byte preflight before row BLOB/text transfer;
  COALESCE accounts for nullable fields independently, followed by per-field CASE guards.
- Definition/contracts <=32768 bytes, bounded object/metadata/job/link/event inventories.

Resource overflow rejects the complete operation; no limit inflation, approximate/partial
fallback, hidden paging or unbounded transfer. Bounds are not scan-cost, peak-memory,
external-concurrency or hostile-database-file safety guarantees.

## Tests and verification attribution

The contract suite covers complete snapshot/context replay; exact aware scalar materialization;
opaque invalid-JSON content as a PURE content boundary; SQL NULL versus JSON null text;
null/empty symbol distinction; canonical hex; source-pin scope invariants; duplicate keys;
aware/naive instant contracts; strict outer context and byte/type bounds. A pure invalid
JSON string does not claim it was admitted by an actual source JSON column.

Native tests reuse the ACTUAL accepted schema-initialization + explicitly SQL-seeded
Bronze fixture, invoke actual Bronze/AuditLedger and the new producer/readers, and compare
all five fields with retained SQL/codec bytes. They cover nullable values, duplicate-key
JSON text as retained by SQL, actual TIMESTAMPTZ and VARCHAR/nullability schema, natural
key independence from symbol, corruption of every scalar, source event/record bytes,
missing rows/links/audits/contracts, extra scoped jobs, same-event other revisions/orphans,
failed review/context pins, real SQL rollback, final-audit failure, second real reader
failure, resource budgets, SQL session timezone invariance, aliases, three read levels
and actual 1000-row native boundary. These are supplied, NOT assistant-executed in the
repository unless explicitly stated in delivery verification.

No writer method/serialization/upsert transformation or original plugin behavior is
invented. SQL fixture seeding is not writer-execution/historical attestation. Isolated
helper/audit/source/codec boundaries, if used for assistant checks, are separately
reported and are NOT native producer/reader E2E. Syntax/archive checks are not Ruff,
mypy, Windows/uv evidence, repository/full pytest or operational acceptance.

## Applying absent additions / new-work verification

Copy absent additions only; STOP/compare if a destination exists. No accepted dependencies,
QA repairs, decision-evidence Silver, pyproject/lock, runtime log or scripts/qa are replaced.
Preserve logs/live_status.json. No PowerShell runner, per-payload SHA256 manifest or
standalone verifier is delivered. Distributed pytest dependency work remains unchanged;
parallel safety/speedup is not certified. Prior user-confirmed fc3f714 QA stays CLOSED.

    uv run python -c "import sys; print(sys.executable); print(sys.version)"
    uv run pytest tests/data_platform/test_legacy_evidence_snapshot_silver_contract.py -q
    uv run pytest tests/data_platform/test_legacy_evidence_snapshot_silver.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Check untracked additions for whitespace too. No assistant Git/worktree, commit/push,
current Windows/uv interpreter or real-data release is claimed. All data/production/
authority/trading/cutover holds remain. This is source-linked persisted Silver, not
Gold, payload interpretation, eligible publication/admission or native decision replay.
