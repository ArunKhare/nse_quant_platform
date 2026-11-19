# Audited retained daily-RV Bronze preservation

## Scope and status

This additive package extends the accepted `legacy_daily_rv` codec without replacing it.
It implements read-only retained SQL capture, actual native Bronze/AuditLedger production,
original-recording verification, and verified in-memory projection through that codec.
It does NOT implement persisted Silver, Gold, publication, decision admission, recovery,
legacy-loop cutover, or real-data migration release.

User-reported baseline: ecadafd passed QA/tests; HEAD is feat/medallion-feature-store at
that commit. The reported origin pointer remains 096c221. No independent Git inspection,
commit, push, Windows execution, or current-worktree claim is made.
The historical provisional wording in the accepted codec document does not reopen its QA.

## Additive installation

Archive members are only:

- src/nse_quant/data_platform/legacy_daily_rv_bronze.py
- tests/data_platform/test_legacy_daily_rv_bronze_native.py
- docs/LEGACY_DAILY_RV_BRONZE.md

Copy absent additions only. If any destination exists, STOP and compare; do not overwrite.
Do not replace accepted dependencies or alter logs/live_status.json. No QA runner, manifest,
ZIP-verifier script, dependency update, or initialization/cutover CLI is included.

## Contract and source semantics

Recording profile: legacy-daily-rv-bronze-recording@1.
Command: migrate.legacy_daily_rv_snapshot@1.
Source: legacy_daily_rv_table_snapshot.
Payload format: accepted legacy-daily-rv-snapshot@1.
Origin: legacy_snapshot, never original provider HTTP/WS evidence.

Only a main.daily_rv_observations BASE TABLE with exact ordered names/types is supported:
symbol VARCHAR, trading_date DATE, rv DOUBLE, observation_count BIGINT.
Every cell must be non-null and correctly typed. Constraints are not independently
attested by the artifact; actual non-null values and unique stored keys are checked.
No alternative schemas, views, filters, pagination, date interpretation, or partial tables.

Stored RV is legacy-derived finite binary64. Signed zero is preserved via hex. Negative
and zero RV and nonpositive counts remain retained observations, flagged by the accepted
projection rather than repaired. No native RV, session, calendar, annualization or
statistical-method validation is asserted. DATE remains a label, not a midnight instant.
INSERT OR REPLACE history cannot be recovered from retained rows. Import time is a supplied
import receipt observation, not provider availability, independent time, or issuer authority.
Source labels and code revisions are declarations, not independently authenticated roots.

## Capture and preservation

`capture_daily_rv(source, source_label=...)` requires an owned read-only SQL connection
with no outer transaction. It reads the whole table in one transaction, validates its
exact schema, preflights row count and aggregate/max symbol bytes before transfer, applies
an independent SQL CASE guard to text, and invokes the actual accepted codec. Ordering and
key uniqueness are defined by that codec. Rejected captures roll back.

`preserve_daily_rv(source, bronze, source_label=..., expected_snapshot_id=...,
imported_at=..., actor_id=..., code_revision=...)` requires separate databases, a file-backed
initialized dedicated Bronze target, and no external transaction. Initialize new empty
native targets explicitly using the actual AuditLedger.initialize and
BronzeEventStore.initialize APIs; production does not initialize or adopt targets.

Two actual complete captures must agree with the reviewed snapshot pin. The producer
calls actual append_batch with one event plus the full artifact and requires exactly one
new variant. It returns source_label, snapshot_id, capture_event_id, envelope_hash,
recording_fingerprint, row_count, job_id, and false decision_eligibility_asserted.

First-write scope binds recording profile plus source label, deliberately excluding the
reviewed snapshot pin, actor, code revision and import clock. A failed reviewed pin cannot
be healed by changing those fields. Prior scoped jobs, variants, batches or a pre-existing
artifact for the reviewed hash block adoption. A genuinely different source label is a
new declared source scope, not recovery of the previous one. Labels cannot be changed to
claim repaired history. Caller serialization is required; no multi-writer guarantee.

Native append_batch owns its domain transaction. A failure inside the append transaction
rolls back artifact/event/batch writes, while the audit job remains failed. A failure after
a successful native domain commit does not undo that commit or permit adoption.
Final SUCCEEDED is separate: missing/failed final audit blocks reading and repeat writes.

## Original recording and current source checks

`read_daily_rv_bronze(readonly_bronze, source_label=..., snapshot_id=...,
capture_event_id=..., envelope_hash=..., expected_recording_fingerprint=...)`
reconstructs the full payload and envelope, original scoped job, exact three-state audit,
complete artifact and native batch fingerprint/counts/sequence. It checks one original
variant and binds recording clocks and metadata in the separately reviewed fingerprint.
It then calls actual codec.derive_records. Those records are NOT persisted Silver.

Payload and artifact transfers have independent SQL CASE byte guards; metadata row counts
and serialized aggregate bytes are bounded, and potentially oversized text uses SQL guards.
Oversized nullable audit reason/parent fields use a non-null rejection sentinel rather
than being silently reinterpreted as legitimate NULL. Payload and artifact hashes are
recomputed; a matching hash alone is not audit or source authenticity.

`revalidate_daily_rv_source(readonly_legacy, readonly_bronze, **reader_pins)` separately
compares two current whole-table SQL captures with the original pin, bracketed by pinned
Bronze reader calls. This is sequential equality observation, NOT an atomic cross-resource
snapshot or file-byte authentication. Retained reading does not require the legacy database
and can succeed when current legacy SQL differs; current-source revalidation must then fail.

Owners close before read-only reopen. Same-file aliases are rejected without closing caller
handles. All new SQL mutations and test assertions use actual quoted catalog.schema.table
identifiers. No source file hashing, runtime attestation or strategy replay is claimed.

## Independent limits

Accepted codec limits remain unchanged: 1..1000 complete rows; symbol <=65536 UTF-8 bytes;
snapshot <=1048576 bytes; projected record <=70000 bytes; projected aggregate <=4194304
bytes. SQL aggregate symbol bytes <=1048576 is a transfer preflight, not a replacement for
the stricter final canonical artifact bound. Metadata <=32768 serialized bytes per bounded
query; envelope <=8192 bytes. Job/history/batch/variant queries use independent small
row limits. These are transfer/content bounds, not guarantees on database scan costs,
DuckDB allocator memory or hostile on-disk database safety.

## Tests and verification attribution

New repository test module uses actual accepted codec, AuditLedger and BronzeEventStore,
real synthetic file-backed DuckDB sources/targets, explicit owner closure and read-only
reopen. It covers producer/reader/current-SQL integration; retained vs current-source
separation; failed reviewed-pin non-healing; payload/artifact/audit/clock/job tampering;
source limits/schema/views/null/nonfinite/duplicate keys; signed zero; cursor aliasing;
original orphan refusal; native SQL domain rollback; and separate final-audit failure.
The drift test intentionally substitutes a changed result AFTER a real second SQL capture;
that is negative-boundary injection, not authentic concurrent-source evidence.

Assistant execution in this delivery:
- New implementation and tests compile under isolated Python 3.12.8.
- Seven isolated SQL capture probes pass with actual DuckDB 1.2.2 and a manually
  transcribed subset of the accepted codec. Audit/Bronze imports were placeholders and
  were not exercised. This is NOT actual native producer/reader integration or E2E.
- Archive exact-member uniqueness, CRC, nonempty payloads and payload-byte equality checked.
- Static line-length/whitespace checks applied to additions; not a substitute for Ruff.

NOT run: repository native test module, repository data-platform/full suites, Windows/uv
interpreter check, Ruff, mypy, git diff --check, actual native producer/reader integration.
No accepted baseline QA is pending or reopened; these are NEW-package verification gaps.
New native integration tests must be run in the actual checkout before acceptance.

Required repository checks follow the existing project instructions: verify interpreter
through uv; run focused new tests, data-platform tests and full tests; run configured Ruff,
mypy and diff whitespace checks including untracked additions. Do not recreate scripts/qa.
Real-data import, positive decision admission, recovery/adoption and cutover remain held.
