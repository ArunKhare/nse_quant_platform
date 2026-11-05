# Persisted source-linked retained decision-evidence Silver

## Scope and source inspection

This additive profile persists complete accepted decision-evidence observations from
actual retained native Bronze. It is not original plugin/strategy decision replay,
verified availability, evidence interpretation, admission or consumer cutover.

Store: legacy-decision-evidence-silver-recording@1.
Command: normalize.legacy_decision_evidence@1.
DatasetContract: silver.legacy_decision_evidence_observations / 1 / APPEND_REVISIONS.
The accepted observation codec/record bytes remain unchanged; no accepted dependency
or Bronze payload is reconstructed/replaced by this ZIP.

Actual current Bronze implementation, its actual-writer tests and analogous native
regime-policy Silver store were retrieved. Repeated targeted retrieval returned the
Bronze module instead of the complete decision-evidence codec file. The implementation
therefore uses only interfaces exercised by that actual source/tests: SCHEMA, VERSION,
DEFINITION, canonical/sha/pin/label/parse, replay_snapshot, derive_records, encode_cell
and wall_fields. It does not guess the writer's JSON/available conversion or implement
a replacement codec. The exact seven-column dependency/version is checked before use.

The retrieved Bronze documentation identifies 3ffa8cf/8489d2f as its delivery baseline;
this is not independently inspected current Git or a new user QA confirmation. All
previously user-confirmed QA remains closed. No assistant repository/Windows/uv/Git
worktree, full hash, commit or push claim is made. Source retrieval is not a checkout.

Only disposable synthetic fixtures are authorized. Real-data loading/migration,
production publication, identities/keys/policies/authority registration, trading and
cutover remain HELD. No strategy, portfolio risk, broker or execution producer is called.

## Exact typed stored semantics

All seven source fields are retained and materialized without changing their meaning:

    evidence_id VARCHAR
    run_id VARCHAR
    ts TIMESTAMP
    symbol VARCHAR
    plugin VARCHAR
    available BOOLEAN
    payload_json VARCHAR

All are required/non-null by this profile, as in the accepted snapshot contract.
Primary evidence ID AND natural (run_id, ts, symbol, plugin) axes are reconciled by
complete accepted snapshot replay. Dedicated Silver also has per-revision uniqueness
constraints on both axes. Primary-ID canonical order is retained, not invented causal
or chronological decision order. UUID/plugin/run labels are not authenticated identity.

The source ts is NAIVE WALL FIELDS, not an instant. It is materialized as TIMESTAMP,
never TIMESTAMPTZ. Encoded canonical wall text has exactly six fractional digits;
zero microseconds remains .000000. Inversion uses datetime.fromisoformat plus actual
wall_fields roundtrip, not timezone assignment or astimezone on source values.
No UTC/IST, epoch, economic-at or original-availability instant is inferred.

Native recorded_at, audit and import clocks are separate aware observations using the
existing aware-clock serializer. Fingerprint metadata explicitly converts the stored
naive SQL timestamp back through wall_fields BEFORE using that serializer. This avoids
both assigning a timezone and accidentally rejecting valid wall tuples as aware metadata.
SQL session timezone changes must leave wall fields AND recording fingerprint unchanged.
Fold/offset/history information lost by legacy storage is not recovered.

available is exact stored BOOLEAN, including true. It is not overwritten to false or
relabeled as independently verified availability. Native eligibility/availability flags
remain those of the accepted exact record codec, separate from this stored scalar.
Original caller representations already coerced by SQL cannot be recovered.

payload_json is exact opaque stored TEXT. Invalid JSON, duplicate/unknown keys,
whitespace and embedded eligible/available flags are preserved; no JSON parser is
called on that field. Outer snapshot/context/record JSON remains separately strict.
No payload/scalar reconciliation, policy authorization or plugin causality is invented.

Original classification and explicit unknown/null/false limitations are preserved
byte-for-byte, including RETAINED_LEGACY_DECISION_EVIDENCE_NOT_ADMISSION,
stored_ts_instant/source_timezone/original_availability_at null, and false payload
interpretation, native decision replay, publication and decision eligibility.

## APIs and actual native producer path

legacy_decision_evidence_silver_store.py:

- DecisionEvidenceBronzePins(source_label, snapshot_id, capture_event_id,
  envelope_hash, recording_fingerprint)
- initialize_decision_evidence_silver(empty_dedicated_file)
- observe_decision_evidence_bronze(readonly_bronze, pins=...) -> bounded full context
- persist_decision_evidence_silver(readonly_bronze, initialized_silver, pins=...,
  expected_context_sha256=..., actor_id=..., code_revision=...)
- read_decision_evidence_silver(readonly_silver, revision_id=...,
  expected_recording_fingerprint=...)
- revalidate_decision_evidence_silver(readonly_bronze, readonly_silver, revision_id=...,
  expected_recording_fingerprint=...)
- revalidate_decision_evidence_silver_source(readonly_legacy, readonly_bronze,
  readonly_silver, revision_id=..., expected_recording_fingerprint=...)

Context retains the COMPLETE original legacy snapshot bytes under bounded hex, all
reviewed Bronze pins and the new store version. Every original source ordinal and
exact accepted projected record is persisted; full scalars and native event link are
materialized. There is no caller-successful record/context import into the producer.

observe calls ACTUAL read_decision_evidence_bronze, ACTUAL read_recording_bytes,
checks its separately reviewed recording fingerprint, derives full content using
ACTUAL accepted codecs, and repeats the public reader. The producer requires a
separately reviewed context hash and repeats the complete native observation again.
No direct raw legacy SQL substitute or fabricated successful lower-source result is
used as source proof. Deterministic retained reconstruction is not independent audit
attestation; native producer/current-source readers still establish original obligations.

## First-write, transaction and original obligations

First-write scope binds profile version and native capture_event_id only. Source label,
snapshot/envelope/recording review pins, context hash, runtime/actor/revision labels
cannot heal a failed attempt for that SAME native event. A genuinely different event
is another subject, not authenticated namespace authority or recovery of the old job.
The scope deliberately excludes more review pins than older family-specific profiles;
those accepted contracts are unchanged.

Any original set/attempt/scoped job or orphan row for the native event blocks before
source observation. The producer uses actual AuditLedger and DatasetContract. Complete
set/context, EVERY observation and original attempt link commit in one domain transaction.
A domain error rolls them all back but leaves the original failed audit obligation.
Final SUCCEEDED audit is separate. Committed content without original success is
unreadable and cannot be adopted. Successful retries are also deliberately disallowed.
No repair, deletion, reset, recovery, supersession or old-good fallback exists.

Retained reader verifies exact profile/contract definition, complete snapshot and
projected record bytes, all seven scalars and materialized indices, revision/scope,
original attempt/job/config and exact three-phase original audit. Queries include
same-event rows under OTHER revisions so a good subset cannot hide orphan coverage.
A separately reviewed recording fingerprint binds clocks, scalars and all selected
recording/audit metadata in addition to revision/content identity.

This verifies application recording integrity, not DB permissions or an independently
authenticated root against someone who rewrites storage and supplies new trusted pins.
Object inventory/definition contracts and full materialized content are verified; no
independently authenticated source constraint-DDL or hostile-file safety claim is made.

## Three distinct read/revalidation levels

1. Retained Silver replay: original Silver recording/audit and complete retained
   snapshot/projected/scalar reconciliation, without consulting current Bronze/legacy.
2. Current native Bronze revalidation: two complete actual current Bronze observations
   compared to retained full context, bracketed by pinned Silver reads.
3. Current legacy SQL revalidation: additionally invokes actual accepted whole-table
   source revalidation, then repeats native/Silver checks.

Changed current legacy SQL does not invalidate unchanged original native evidence.
Missing current original Bronze audit blocks level 2/3 while retained Silver can still
replay. SQL/operational errors propagate; they are not unavailable/accepted business
outcomes. Repeated observations do not establish an atomic multi-database snapshot,
source-file hash, independent time truth or original plugin/decision execution replay.

Caller owns connections, no outer transactions/shared writers. Explicit initialization
requires an empty dedicated file; partial initialization cannot be adopted. Public
readers require actual readonly mode. Close writers before read-only reopen. Actual
same-live-file cursor aliases reject while parent owners remain usable. SQL mutations
and assertions quote actual catalog.schema.table, including silver.duckdb/silver schema.

## Independent resource bounds

All accepted Bronze/source limits remain unchanged:

- 1..1000 whole-source rows; no selected windows/prefixes/paging.
- Snapshot <=1048576 bytes; source text <=65536 UTF-8 bytes/cell.
- Full wrapper context <=2200000 bytes, bounded before strict parsing/hex decoding.
- Exact records <=524288 bytes each and <=4194304 aggregate, checked before persistence.
- Materialized text independently <=65536 bytes/cell and <=1048576 aggregate.
- SQL count/aggregate/max record and scalar-byte preflight BEFORE transferring row BLOBs
  or scalar text; independent CASE guards remain on transferred fields.
- Metadata definitions/contracts <=32768 bytes, bounded schema inventory and overflow
  row detection for original jobs/attempts/events; guarded identifiers.

No limits are inflated for this new store. Escaping can independently exhaust record/
context bounds. Bounds do not guarantee scan cost or peak process memory. No partial
success, approximate fallback, implicit paging or unbounded artifact transfer.

## Tests and verification attribution

New tests reuse the retrieved actual-writer/native Bronze fixture helper, then invoke
the new native producer/readers. They compare all seven materialized fields to actual
source-codec bytes, retain opaque/duplicate-key TEXT and true stored booleans separately
from false native eligibility, and check wall timestamps remain naive at microsecond
precision. Tests cover all materialized scalar/record corruption, original rows/links/
audits/contracts, same-event variants, review/context-pin failures, extra scoped jobs,
orphan adoption refusal, real SQL domain rollback, final-audit failure, second actual
source-read failure, record/scalar/context budgets, session timezones, live-file aliases,
three read levels and actual complete 1000-row source capture through native Silver.
These repository-dependent tests are supplied, NOT assistant-executed.

The legacy writer's serialization expressions were not independently reconstructed:
actual source SQL/accepted codecs are the test oracle. Native fixture reuse is not
proof that those tests ran in this assistant environment. Any isolated source/audit/
codec adapters are explicitly attributed separately in delivery verification and are
not native E2E. No accepted dependency/transcription or fake source implementation is
delivered in the ZIP.

Syntax/line lengths/whitespace and archive nonempty/exact members/uniqueness/CRC/payload
equality are checked before final delivery. They do not imply Windows/uv, actual
repository focused/full pytest, Ruff, mypy, Git or platform operational acceptance.
Earlier user-confirmed QA stays CLOSED; new verification gaps do not reopen it.

## Applying absent additions and new-work verification

Copy absent additions only; STOP/compare if a destination exists. No accepted source,
QA repair, logs/live_status.json, pyproject/lock or scripts/qa is replaced. No PowerShell
runner, per-payload SHA256 manifest or standalone ZIP verifier is supplied. Distributed
pytest dependency work is untouched; parallel safety/speedup is not certified here.

    uv run python -c "import sys; print(sys.executable); print(sys.version)"
    uv run pytest tests/data_platform/test_legacy_decision_evidence_silver.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Check untracked additions for whitespace as well. Package QA is not platform acceptance
or a release of data/production/authority/trading/cutover holds. evidence_snapshots is
a distinct remaining family; this package does not claim to migrate it or add Gold,
publication, verified availability or replay original native/legacy decisions.
