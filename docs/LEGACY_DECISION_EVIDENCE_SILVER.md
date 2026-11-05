# Audited persisted decision-evidence Silver with a separate naive-wall clock lane

## Reported baseline, access and additive delivery

Latest supplied Git pointers: de2f3a1 at reported matching HEAD/origin
feat/medallion-feature-store, predecessor 3ffa8cf. No independent Git/worktree/Windows
inspection, repository write, commit, push or additional QA result is invented. Earlier
user-confirmed QA remains CLOSED; historical delivery-time "not run" attribution does
not reopen it. New-package verification is a separate matter.

Access was rechecked; no repository/filesystem/execution connector was returned. Project
Sources are retrieval only. Current decision-evidence Bronze implementation/tests and
current policy Silver pattern were retrieved. Direct codec-source requests returned the
Bronze file instead; the codec's current implementation was not independently recovered.
Its interfaces/semantics are established by the CURRENT audited consumer and tests,
including wall_fields, strict bool, source schema, make/replay and projection interfaces.
This consumer IMPORTS the accepted codec unchanged, never inlining/replacing it with an
older generated payload. Isolated transcribed-dependency checks below are labeled separately.

Copy absent additions only; STOP and compare if a destination exists:
- src/nse_quant/data_platform/legacy_decision_evidence_silver_store.py
- tests/data_platform/test_legacy_decision_evidence_silver.py
- docs/LEGACY_DECISION_EVIDENCE_SILVER.md

No accepted dependency replacement, scripts/qa, PowerShell runner, per-payload manifest
or standalone ZIP verifier is included. Do not modify logs/live_status.json, infer
real-data release or cut over consumers. This is persisted source-linked Silver, not an
archive/reporting wrapper or a fake Gold/decision contract.

## Contract and actual native source integration

Recording: legacy-decision-evidence-silver-recording@1.
Command: normalize.legacy_decision_evidence@1.
Dataset: silver.legacy_decision_evidence_observations / 1 / APPEND_REVISIONS.
Projection: accepted legacy-decision-evidence-observation@1, unchanged.
Source: actual legacy-decision-evidence-bronze-recording@1 original-recording reader.

Complete original serialized snapshot bytes are retained in canonical snapshot_hex
context with all reviewed Bronze pins, including its separate recording fingerprint.
Every source ordinal receives exactly one full persisted projection and all seven typed
scalar fields. No partial/good-subset selection or discarded unavailable rows.

observe_decision_evidence_bronze calls actual public pinned native readers, retrieves full
bytes through actual read_recording_bytes, checks the observed recording fingerprint,
rebuilds complete context/projections and repeats the public read. Every projected byte
must match. Persistence repeats that complete native observation and requires the reviewed
context hash. Operational/corrupt upstream errors propagate under audited failed jobs,
never fabricated successful lower-source DTOs or native availability observations.

## Typed scalars and the two-clock rule

All source fields are materialized: evidence_id, run_id, ts, symbol, plugin, available,
payload_json. All remain required as in the accepted retained-cell contract.
- ts is a genuine SQL TIMESTAMP WITHOUT timezone, NOT TIMESTAMPTZ, epoch or inferred UTC.
- available is SQL BOOLEAN and explicitly checked as Python bool, never integer 0/1 aliases.
- payload_json is exact VARCHAR TEXT, not parsed/normalized JSON. Arbitrary non-JSON,
  whitespace, duplicate keys, embedded available/eligible claims and empty strings survive.
- Opaque IDs/run/plugin/symbol labels are retained, not authenticated identity or issuer roots.

Every scalar/full record/source ordinal is reconstructed from the full original snapshot
on read. Original primary evidence_id uniqueness and natural (run_id,ts,symbol,plugin)
uniqueness are recomputed by the accepted full snapshot codec. Native SQL additionally
has per-revision UNIQUE constraints for BOTH axes, as defense in depth, never substituting
for full replay. Uniqueness is scoped to revision, not arbitrary cross-revision deduplication.

The recording fingerprint handles source ts ONLY through accepted codec.wall_fields,
retaining all calendar/clock/microsecond fields and timezone unknown. It converts the
materialized naive value to canonical wall TEXT before serializing recording metadata.
It never passes source ts to the aware-clock serializer, assigns UTC/IST, calls astimezone
on source wall fields, fabricates an exchange_ts or recovers lost offsets/fold information.

Native import/recording/audit clocks are SEPARATE aware observations using accepted aware
clock helpers. Aware clock normalization uses astimezone(UTC), never replace(tzinfo=UTC).
Session TimeZone changes must not alter wall fields OR the reviewed recording fingerprint;
tests read under UTC and Asia/Kolkata. Source timestamps with zero microseconds retain
.000000 through the accepted codec, not inferred precision or source decimal spelling.

The reader verifies the actual ordered observation column names/types against the reviewed
schema, including TIMESTAMP versus TIMESTAMPTZ and BOOLEAN versus INTEGER. Integer 1 must
not accidentally compare equal to True under Python tuple equality. Exact bool type and
wall-codec checks supplement physical SQL schema validation. No existing accepted schema
or fixture is renamed to conceal a mismatch.

Stored available=True stays retained true; native availability/eligibility are separate.
Classification stays RETAINED_LEGACY_DECISION_EVIDENCE_NOT_ADMISSION. Source instant,
source_timezone, original availability, identity and economic-validity instants remain
unknown/null; payload interpretation, recovered original bytes/history, native decision
replay, publication and decision eligibility remain false. These are NOT original plugin,
strategy/risk/portfolio/execution runs or decision-admission evidence.

## APIs and synthetic workflow

Import nse_quant.data_platform.legacy_decision_evidence_silver_store.

1. Construct EvidenceBronzePins(source_label, snapshot_id, capture_event_id, envelope_hash,
   recording_fingerprint) from actual reviewed native Bronze evidence.
2. Open native Bronze read-only; Silver production never opens/probes current legacy SQL.
3. Explicitly initialize a separate EMPTY dedicated file-backed target using
   initialize_decision_evidence_silver(target). Existing/foreign/partial stores refuse;
   no automatic repair/adoption. Current catalog itself must be file-backed, not memory
   with a file attached. Caller owns connections, provides no outer transaction and
   serializes writers. No multi-writer coordinator is asserted.
4. Call observe_decision_evidence_bronze(bronze, pins=pins), review full context hash,
   then persist_decision_evidence_silver(bronze, target, pins=pins,
   expected_context_sha256=..., actor_id=..., code_revision=...).
5. Retain/review returned revision_id and recording_fingerprint SEPARATELY. Additional
   receipt fields are row_count, job_id and decision_eligibility_asserted=false.
6. Close writer owners BEFORE read-only reopen. Use read_decision_evidence_silver(
   readonly_silver, revision_id=..., expected_recording_fingerprint=...) for retained replay.
7. Use revalidate_decision_evidence_silver(readonly_bronze, readonly_silver,
   revision_id=..., expected_recording_fingerprint=...) for additional current native equality.

The real silver.duckdb catalog/silver schema collision is preserved and tested, not renamed.
All new mutations/assertions quote actual catalog.schema.table. Same-live-file aliases use
separate cursor handles, reject without closing parents and retain real owners. Code revision
is a supplied full lower-case 40-character declaration, not a full hash invented from short
hashes or authenticated Git/interpreter/issuer/build truth.

## Scope, atomic writes and original obligations

First-write scope = profile + source label + source snapshot ID + capture-event ID.
Envelope/recording pins, context-review hash, actor/revision labels and recording clocks
are excluded. Changing excluded fields cannot heal the same failed source-observation
scope. New source artifacts are new revision scopes, not recovery. Labels do not establish
legitimate source namespace/governance authority.

Prior scoped jobs/sets/attempt links block repeats. Orphan observations for the capture
event also block adoption after set/job/link deletion. No repair, implicit retry-adoption,
recovery or orphan healing API exists. Original Bronze obligations are independently
verified by the actual native reader. Partial initialization cannot be silently adopted.

Native AuditLedger job precedes source observation. Context/set, every full projection,
all scalar indices and attempt link commit atomically in ONE domain transaction. Second-
INSERT failure rolls back partial domain writes while failed audit remains. Final audit
SUCCEEDED remains separate from domain commit; failure leaves committed rows unreadable
and non-adoptable. No positive decision or release permission results from any receipt.

## Three distinct replay/revalidation questions

read_decision_evidence_silver requires read-only dedicated storage and exact reviewed
revision/recording pins. It checks supported definitions/contract/physical scalar types,
full context/snapshot, all source ordinals/links/scalars/bytes, revision identity, attempt
link, original single scoped job and exact PLANNED/RUNNING/SUCCEEDED history.
The recording fingerprint binds selected set/observation metadata and clocks, all scalar
indices (with source wall fields serialized separately), original jobs/events/links and
source/context hashes. Registration clocks are not independent time truth.

Offline hash/replay proves retained content, NOT authentic declared Bronze pins or original
provider/decision provenance. Retained reading never probes Bronze or legacy SQL and can
succeed after Bronze is missing or its audit no longer validates.

revalidate_decision_evidence_silver requires TWO repeated actual pinned native Bronze
observations equal to frozen full context, bracketed by pinned Silver reads. Changed or
corrupt original Bronze audit fails that check while retained Silver may still replay.
Current legacy SQL equality remains accepted Bronze's separate
revalidate_decision_evidence_source check; tests mutate legacy SQL while native layers
remain equal, then separately corrupt original Bronze audit. Sequential observations are
NOT atomic cross-resource snapshots, source-file hashes or replay of unrun domain stages.

Definitions bind supported codec/source definitions and actual DatasetContract, not whole-
repository source hashes, independently authenticated interpreters/builds/issuer roots,
environment recovery or silent reinterpretation of changed definitions.

## Independent bounds and transfer ordering

Accepted evidence limits remain unchanged: 1..1000 rows; five text cells <=65536 UTF-8 bytes;
snapshot <=1048576 bytes; projection <=524288 bytes and <=4194304 bytes aggregate.
Complete canonical hex-snapshot context <=2200000 bytes. Hex <=2097152 characters is checked
BEFORE decode; strict reconstruction rejects casing/whitespace aliases, extra keys or
source mismatch. Wall-field/boolean spellings remain governed by the accepted codec.

Materialized text scalar aggregate <=1048576 bytes independently; snapshot encoding already
includes those strings, so this does not inflate source limits. SQL preflights count,
aggregate/max record bytes, aggregate scalar bytes and EVERY text/ID overflow in one read
transaction BEFORE transferring observation rows. Independent CASE guards remain on
materialized text, record bytes and IDs. Context/definition/contract/metadata/physical-column
and catalog inventories have independent bounded guards and row limits. Accepted metadata
<=32768 serialized bytes per query remains. Resource overflow rejects the whole recording,
not selected business rows. Bounds are not scan-cost, allocator/process-memory, hostile-file
safety or external concurrency guarantees. No paging, partial success or silent limit growth.

## Tests and honest verification attribution

Delivered tests import actual DuckDBStore writer, accepted native evidence Bronze
producer/readers and native AuditLedger/BronzeEventStore with new Silver. Positive fixtures
use real writer/upsert calls, plus an explicit opaque TEXT boundary through actual SQL,
then native Bronze, persisted Silver, writer closure and read-only reopen. Source boolean/
payload assertions compare against native retained records, not assumed writer formatting.
No original plugin/domain computation, authentic changed-source permission or decision replay
is claimed by synthetic dict inputs.

Coverage includes all seven scalar mutations; naive TIMESTAMP and strict BOOLEAN physical
types; rejected BOOLEAN-to-INTEGER drift; microseconds/session timezone; both SQL key
constraints; original bytes/coverage/context/record/aggregate/cell/link/audit/clock faults;
reviewed-pin non-healing; native-vs-legacy source checks; missing Bronze; contracts/definitions/
duplicate jobs/orphans; partial SQL rollback; final-audit failure; aliases/init; predecode
hex bound; maximum-payload native persistence with SHORT ID/full payload; and second actual
observation then injected drift. Boundary injections are not authentic source evidence.

Assistant-executed independent checks, Python 3.12.8 / DuckDB 1.2.2:
- New implementation/test syntax compiled; line lengths/trailing whitespace checked.
- 24 actual SQL/materializer probes passed: roundtrip/revalidation, mutation of ALL seven
  fields, record bytes/missing rows/clocks/orphan link, oversized context/record/cell,
  independent scalar aggregate, reviewed-context non-healing, partial second-INSERT rollback,
  audit rejection, BOOLEAN-to-INTEGER schema rejection, both SQL UNIQUE constraints,
  maximum payload and session-timezone invariance. Bronze/audit/contract boundaries were
  substituted; codec/helpers were transcribed from the observed interface/semantic contract.
  These are NOT actual accepted-dependency native integration, actual repository writer/
  codec execution, original domain replay or repository/native E2E QA.
- ZIP exact three-member set, uniqueness, CRC, nonempty payloads and byte equality verified.

NOT run: Windows/uv interpreter check; actual accepted-dependency native chain; repository
focused/data-platform/full pytest; Ruff; mypy; git diff --check; Git untracked whitespace
checks. These are NEW-package verification gaps, not reopening earlier confirmed QA.
Acceptance uses uv/configured tests/lint/types plus tracked/untracked whitespace checks.
No substituted dependencies or external verification wrappers are delivered.

## Operational holds

Retained decision evidence is now represented in this delivered Silver implementation,
not authenticated availability, native decision admission/replay, legitimate identity/
governance/time roots, complete strategy/portfolio inputs, operational recovery, real-data
release or consumer cutover. Existing numerical solvers, research-only admission and legacy
loop remain unchanged. No native-platform completion percentage is claimed.
