# Audited retained decision-evidence Bronze: naive wall fields stay naive

## Baseline, inspection and additive scope

Latest supplied Git: 3ffa8cf at reported matching HEAD/origin feat/medallion-feature-store,
with 8489d2f predecessor. No independent Git/worktree/Windows inspection, repository write,
commit/push or additional QA result is invented. Earlier user-confirmed QA stays CLOSED;
historical "not run" delivery attribution does not reopen it.

Access was rechecked: no repository/filesystem/execution connector was returned. Project
Sources are retrieval only, not executable checkout access. Current policy Silver source
and tests were recovered after retry. The decision-evidence writer signature, seven-column
insert and previously inspected schema/upsert SQL define this retained-data boundary. The
writer's final Python available/serialization expressions were NOT recovered in this turn.
This package does NOT guess those expressions or claim their exact transformation. Its
actual-writer integration compares against raw SQL values produced by the current writer.
Any schema difference fails exact source checks rather than being coerced or repaired.

This separate bounded chunk implements retained decision_evidence whole-table snapshot,
actual native Bronze/AuditLedger preservation, exact source-linked IN-MEMORY observations,
original-recording replay, adversarial/native integration tests and documentation. It is
not persisted evidence Silver, original decision/plugin execution replay, native admission,
operational recovery or consumer cutover. evidence_snapshots is a DIFFERENT family.

Archive contains only:
- src/nse_quant/data_platform/legacy_decision_evidence.py
- src/nse_quant/data_platform/legacy_decision_evidence_bronze.py
- tests/data_platform/test_legacy_decision_evidence_bronze.py
- docs/LEGACY_DECISION_EVIDENCE_BRONZE.md

Copy absent additions only; STOP and compare if a destination exists. Accepted dependencies
are imported unchanged, not replacement payloads. Do not modify logs/live_status.json,
recreate scripts/qa, add a PowerShell runner/manifest/standalone ZIP verifier, change native
admission, infer real-data release or extend the legacy loop.

## Exact retained SQL shape and both key axes

Supported BASE TABLE: main.decision_evidence with exact ordered fields/types:
evidence_id VARCHAR, run_id VARCHAR, ts TIMESTAMP, symbol VARCHAR, plugin VARCHAR,
available BOOLEAN, payload_json VARCHAR. DuckDB reports SQL TEXT columns as VARCHAR.

Required actual cells are all non-null. Primary key is evidence_id; alternate unique key
is (run_id, ts, symbol, plugin). BOTH are recomputed from every retained row. Duplicate
primary IDs under different natural keys or duplicate natural keys under different IDs
reject the complete capture. Source constraint DDL is not independently authenticated by
the artifact; actual values/keys are validated even if a malformed table lacks constraints.

Inspected write_decision_evidence takes run_id, ts, symbol, plugin and an evidence dict.
Its INSERT supplies a new UUID candidate, with conflict handling on the natural key
updating retained available/payload rather than recovering earlier versions. The integration
fixture invokes the ACTUAL method twice on the same key and checks retained row identity,
then compares all stored fields without assuming final JSON formatting/boolean derivation.
There is no source writer patch or fabricated successful lower-source DTO.

Only this entire exact-schema base table is supported: no views, filtered/date windows,
extra fields, changed boolean types, JSON-column substitutions, TIMESTAMPTZ/MS/NS clock
variants, partial captures or hidden paging. Other retained families require new contracts.

## The important clock distinction

Snapshot: legacy-decision-evidence-snapshot@1.
Projection: legacy-decision-evidence-observation@1.
Native recording: legacy-decision-evidence-bronze-recording@1.
Command: migrate.legacy_decision_evidence@1.
Native source: legacy_decision_evidence_table_snapshot; origin_kind=legacy_snapshot.

Stored TIMESTAMP is a NAIVE WALL-FIELD tuple, not an independently known instant. The
codec requires a plain naive datetime from SQL and canonical ISO wall text with exactly
six fractional digits, e.g. 2026-01-01T09:15:00.123456. Zero microseconds retains .000000.
It never assigns UTC/IST, calls astimezone on the source wall tuple, or derives an epoch,
exchange_ts, economic validity, original availability or knowledge cutoff from it.
Timezone/offset/Z spellings and noncanonical wall spellings reject encoded snapshot rows.
Fold information/offsets originally lost by SQL storage are not recovered. Values outside
supported Python datetime representation reject rather than being reinterpreted.

Native imported_at and native audit/recording clocks are SEPARATE aware observations using
the accepted aware-clock helpers. Import time is a supplied import receipt, not original
provider/plugin/decision availability. Native exchange_ts stays None. Source wall values
are retained inside payload/record bytes as strings and never passed to the aware native
metadata serializer. Session timezone changes do not convert stored SQL TIMESTAMP wall
fields; the test explicitly captures under UTC and Asia/Kolkata and compares full bytes.

available is retained as an EXACT boolean: type bool only, not integer 0/1, a string or
NULL in encoded evidence. SQL may already have coerced an original writer input; that
lost caller representation is not recovered. The stored flag is NOT independently
verified availability and does not authorize any platform action. True remains retained
true, not forcibly relabeled false; native eligibility flags are separate and false.

payload_json is exact stored TEXT, NOT a JSON-typed contract. Invalid JSON, whitespace,
unknown/duplicate keys, embedded eligible/available flags and arbitrary text are retained
without parsing or normalization. No payload/scalar availability reconciliation is invented.
Outer artifact JSON is separately strict/canonical and rejects duplicate/unknown structure.

Classification is RETAINED_LEGACY_DECISION_EVIDENCE_NOT_ADMISSION. Each projection retains
all seven fields and snapshot/capture-event/envelope pins plus exact source ordinal.
Stored time semantics explicitly say timezone unknown; stored_ts_instant/source_timezone/
original_availability_at are null. Payload interpretation, original bytes/history recovery,
native decision replay, publication and decision eligibility remain false. Identity and
economic-validity instants remain null. UUID/run/plugin labels are not authenticated roots.

## Actual native capture and first-write persistence

capture_decision_evidence(readonly_legacy, source_label=...) owns one SQL transaction;
caller owns the source with no outer transaction. It verifies exact schema/base-table kind,
preflights count and aggregate/max UTF-8 text bytes, uses independent SQL CASE guards on
every text column, reads max+1 bounded rows and encodes strict wall fields/booleans/text.
Canonical primary-ID ordering is deterministic, not chronology or causal decision order.

preserve_decision_evidence(readonly_legacy, initialized_bronze, source_label=...,
expected_snapshot_id=..., imported_at=..., actor_id=..., code_revision=...)
requires separate resources and a dedicated initialized file-backed current native Bronze
catalog. Initialize NEW targets explicitly through actual AuditLedger.initialize and
BronzeEventStore.initialize. Producer/readers do not initialize/adopt/repair targets.

Two actual complete captures must agree with the reviewed snapshot pin. Full snapshot/
projection validation and resource checks occur BEFORE actual native append_batch, which
retains one event plus the complete artifact and must insert exactly one new variant.
Unknown original HTTP/WS/plugin artifacts elsewhere remain unknown, not recovered Bronze.

Scope = profile + source label, excluding reviewed content/recording pins, actor/revision
labels and clocks. Original scoped jobs/variants/batches or pre-existing reviewed artifacts
block reuse/adoption. Changing excluded fields cannot heal failed scope. A new label is
a new declaration, not original failure recovery or legitimate namespace authority.
Caller serializes writes; no multi-writer coordination or recovery API is included.

Receipt includes source_label, snapshot_id, capture_event_id, envelope_hash,
recording_fingerprint, row_count, job_id, decision_eligibility_asserted=false. Code revision
requires a supplied full lower-case 40-character declaration; no full hash is invented from
user short hashes or independently authenticated Git/interpreter/build/issuer evidence.

## Original recording versus current source equality

read_recording_bytes(bronze, source_label=..., snapshot_id=..., capture_event_id=...,
envelope_hash=...) is a lower-level verifier returning original full bytes/fingerprint.
Public reading additionally requires read-only ownership and a separately reviewed
recording pin; the low-level API is not a substitute for those requirements.

read_decision_evidence_bronze(readonly_bronze, source_label=..., snapshot_id=...,
capture_event_id=..., envelope_hash=..., expected_recording_fingerprint=...)
checks stored event/envelope IDs, full snapshot/envelope, complete artifact, native batch
fingerprint/counts/sequence, original single scoped job and exact original
PLANNED/RUNNING/SUCCEEDED history. The separate recording fingerprint binds selected native
metadata/clocks/audit lineage independently of snapshot identity. Content hashes alone
are not original source authentication, audit proof or replay of original decisions.

revalidate_decision_evidence_source(readonly_legacy, readonly_bronze, **public_reader_pins)
adds two current complete SQL equality observations bracketed by pinned native reads.
Retained replay can succeed when current legacy SQL differs or is unavailable. Sequential
observations are not atomic cross-resource snapshots, source-file hashes or full native
strategy/risk/execution replay. Only capture/verification/projection stages actually run
are represented. Native quote/geometry/window research admission remains unchanged.

Native append/domain commit and final audit SUCCEEDED remain separate obligations. A
native insert failure rolls back artifact/event/batch writes while retaining failed jobs.
Missing final SUCCEEDED after commit blocks original read/adoption. Deleting audits cannot
authorize orphan reuse. No implicit repair, healing, retry-adoption or hold release exists.
Owners close before read-only reopen; same-file aliases use distinct cursor handles,
reject without closing parents and retain owners. Mutations/assertions quote actual
catalog.schema.table names; no fixture renames hide catalog collisions.

## Independent limits

This new family does not inflate any accepted profile:
- 1..1000 complete rows, count preflight and max+1 transfer guard.
- Five text cells <=65536 UTF-8 bytes each, aggregate transferred text <=1048576 bytes.
  Nullable malformed cells cannot hide other byte sizes: COALESCE counts independently.
- Complete canonical snapshot <=1048576 bytes independently of raw-text preflight.
- Projection <=524288 bytes each and <=4194304 aggregate; overflow rejects before append.
- Canonical wall text exactly 26 characters with microsecond spelling and no timezone.
- Envelope <=8192 transferred bytes; inherited metadata <=32768 serialized bytes per
  independently row-bounded query with independent SQL CASE guards.

Raw decoder bytes are bounded before strict outer JSON parsing. Escaping can independently
exhaust artifact/projection bounds; no partial/good-subset success. These limits do not
guarantee scan costs, allocator/process memory, hostile-file safety or external concurrency.

## Tests and honest verification

Delivered tests import actual DuckDBStore.write_decision_evidence, native AuditLedger/
BronzeEventStore and new implementation. Positive fixture uses the real writer/upsert,
then retains an explicit arbitrary-TEXT boundary through actual SQL, runs actual native
producer/readers, closes owners and reopens read-only handles. All fields compare with
raw SQL, not a guessed source serialization. Opaque injected text is a boundary case, not
authentic authorization or full decision-domain E2E evidence.

Coverage includes naive/aware/session-timezone boundaries; strict booleans; primary AND
natural keys; all-field reconciliation; schema/view/NULL/key/count bounds; text limits
with SHORT IDs/full payloads; stored true vs false native eligibility; original recording
tampering; current source separation; non-healing; SQL rollback; final-audit failure;
aliases/orphans; projection overflow before append; strict outer JSON; and a second real
capture followed by injected drift. Drift is not authentic changed-source evidence.

Assistant-executed, isolated Python 3.12.8 / DuckDB 1.2.2:
- New implementation/test syntax compiled; line lengths/trailing whitespace checked.
- 26 actual SQL capture/projection cases passed: true/false, zero microseconds, opaque
  TEXT, view/aware-schema/NULL/key/count rejection, canonical/projection/aggregate bounds,
  every text column cell boundary, and session timezone invariance.
- Seven additional strict encoded-type checks rejected integer/string/NULL booleans and
  aware wall-clock inputs. Shared strict JSON/catalog/read-only helpers were transcribed;
  native audit/Bronze import placeholders deliberately raise if exercised and were NOT
  exercised. These are NOT native producer/reader integration, actual repository legacy
  writer execution, original plugin/decision replay or repository/native E2E QA.
- ZIP exact four-member set, uniqueness, CRC, nonempty payloads and byte equality verified.

NOT run: actual accepted-dependency legacy/native chain, Windows/uv interpreter check,
repository focused/data-platform/full pytest, Ruff, mypy, git diff --check or Git untracked
whitespace checks. These are NEW-package verification gaps, not reopening earlier accepted
QA. Acceptance uses uv/configured tests/lint/types and tracked/untracked whitespace checks.
No transcribed dependencies/placeholders or external verification wrappers are delivered.

## Remaining operational holds

Persisted source-linked decision-evidence Silver remains next. No recovered source timezone,
independent availability, native decision admission/replay, authenticated governance/identity,
complete strategy/portfolio inputs, operational recovery, real-data release, cutover or
completion percentage is claimed. Legacy loops and accepted solvers/contracts are unchanged.
