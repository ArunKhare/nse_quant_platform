# Bounded native Bronze for retained evidence_snapshots

## Baseline and inspected scope

User-confirmed f239b89/5ffa108 decision-evidence Silver QA remains CLOSED. This is a
DIFFERENT retained family, evidence_snapshots, not a rebuild of decision_evidence or
an extension of its naive-wall contract. Supplied HEAD/origin at f239b89 is accepted;
no independently inspected Git/worktree/Windows state, full hash or push is invented.

The actual DuckDBStore DDL was retrieved with these ordered fields:

    run_id VARCHAR
    ts TIMESTAMPTZ
    symbol VARCHAR
    plugin_name VARCHAR
    payload_json JSON
    PRIMARY KEY (run_id, ts, plugin_name)

DuckDB reports TIMESTAMPTZ as TIMESTAMP WITH TIME ZONE. Only the ENTIRE exact-schema
main.evidence_snapshots BASE TABLE is supported. No views, filtered window, extra
columns, naive TIMESTAMP or VARCHAR payload substitutions are adopted. Keys must be
known and unique even for malformed tables lacking constraints. Symbol is NOT a key;
changing symbol does not justify two rows under the same run/time/plugin key. Nullable
symbol and payload remain nullable rather than imputed. Other source families need
separate contracts; no join to decision_evidence or evidence-id mapping is invented.

Targeted retrieval did NOT recover the evidence-snapshot writer method, its signature,
serialization or upsert expressions. This package does not guess them or label a made-up
method call actual-writer E2E. Native fixtures initialize the actual DuckDBStore schema
and seed disposable data through explicit SQL, compare against retained SQL, then call
actual new native Bronze producer/readers. SQL-fixture seeding is NOT original plugin
execution, writer serialization or historical mutation attestation. Lost/overwritten
versions are not recovered, regardless of how the original caller wrote retained rows.

Access recheck returned no repository/filesystem/execution connector; Project Sources
are retrieval, not an executable checkout. Accepted daily-RV common helper APIs and
native Bronze/AuditLedger interfaces were inspected through their actual usages in
current decision-evidence/policy source families. No accepted dependency is replaced.

## Profiles and semantics

Codec: legacy-evidence-snapshot-table@1.
Observation: legacy-evidence-snapshot-observation@1.
Native recording: legacy-evidence-snapshot-bronze-recording@1.
Command: migrate.legacy_evidence_snapshots@1.
Native source: legacy_evidence_snapshot_table_snapshot, origin_kind=legacy_snapshot.

All five stored fields are retained. ts is a retained application SQL instant, normalized
with astimezone(UTC), NOT independent market/plugin/decision availability or economic
validity. Original timezone labels, original caller spelling/fold and discarded clocks
are not recovered. Naive source timestamps reject; decision_evidence's different naive
TIMESTAMP semantics are unchanged. Import/native audit clocks are separate aware
observations; imported_at is an explicit import receipt, never original availability.
Native exchange_ts remains None.

payload_json is read using CAST(payload_json AS VARCHAR) and retained EXACTLY as returned
by stored SQL. It is not parsed, normalized, mined for available/eligible flags or checked
against scalar assertions. Whitespace, duplicate keys, scalar/array/object JSON, unknown
claims and escape spelling are kept to the extent retained by SQL. No promise is made
that SQL storage preserved original writer/provider bytes or JSON spelling before storage.

SQL NULL payload is None in the outer artifact; JSON literal null is stored text "null".
They are distinct. Nullable symbol is similarly distinct from an empty string. The pure
content constructor treats payload as opaque text and does not revalidate JSON syntax:
it proves retained-shaped content consistency, NOT that those bytes came from a JSON
column. Actual native capture verifies the real JSON SQL column and source bytes.
Invalid raw JSON cannot be inserted as JSON merely by passing the pure constructor.

Outer artifact JSON is independently strict/canonical, rejecting duplicate/unknown
outer structure and nonfinite literals. Inner payload text is never interpreted by the
outer parser. Canonical key-byte ordering is deterministic, not causal decision order.

Classification: RETAINED_LEGACY_EVIDENCE_SNAPSHOT_NOT_ADMISSION.
Every projected row carries source label, snapshot/event/envelope pins and full source
ordinal/key/fields. stored_ts_instant records the retained normalized SQL instant only;
original_availability_at/canonical identity are null. Payload interpretation/JSON syntax
revalidation, original provider-byte/history recovery, native decision replay, verified
availability/economic validity, publication and decision eligibility remain false.
There is no invented available scalar: that column does not exist in this family.

## Actual native producer and reader

- capture_evidence_snapshots(readonly_legacy, source_label=...)
- preserve_evidence_snapshots(readonly_legacy, initialized_bronze, source_label=...,
  expected_snapshot_id=..., imported_at=..., actor_id=..., code_revision=...)
- read_recording_bytes(bronze, source_label=..., snapshot_id=..., capture_event_id=...,
  envelope_hash=...): low-level original verifier, not a public read-only/review-pin substitute.
- read_evidence_snapshot_bronze(readonly_bronze, source_label=..., snapshot_id=...,
  capture_event_id=..., envelope_hash=..., expected_recording_fingerprint=...)
- revalidate_evidence_snapshot_source(readonly_legacy, readonly_bronze, **reader_pins)

One owned source transaction verifies exact types/base-table shape, preflights whole-row
count and aggregate/max UTF-8 scalar bytes, then independently CASE-guards every text/JSON
transfer. max+1 transfer guards overflow; no paging or LIMIT-prefix promotion. Complete
codec/key/artifact checks follow. No caller-successful snapshot DTO is imported as source
proof by the native preservation API.

Two actual complete captures must match each other and the separately reviewed snapshot
pin. Full projection/resource validation occurs BEFORE native append_batch. Actual
BronzeEventStore/AuditLedger retain one native event and complete snapshot artifact in one
batch, requiring exactly one inserted variant with no retry/conflict/already-committed reuse.
Initialize NEW native Bronze explicitly through actual accepted initialization APIs.
No acquisition, backfill, registration or production publication is called.

First-write scope binds profile version plus source label, excluding review/content pins,
import clock and actor/revision labels. Prior scoped jobs, variants, batches or reviewed
artifact block before capture. A new label is a new declaration, not legitimate namespace
authority or recovery of an original failed obligation. Concurrent writers/outer
transactions are unsupported; caller serializes ownership.

Retained reader reconciles event/envelope/hash/source/session IDs, complete snapshot and
artifact, batch counts/fingerprint/sequence, exact original job/config/scope and exact
PLANNED/RUNNING/SUCCEEDED history. Variant scope/job coverage, batches under original job
and artifacts under original job are checked, not just a good matching content subset.
A separately reviewed recording fingerprint binds selected native metadata/clocks/audits
in addition to the content hash. Hash equality is not independent original authenticity.

Native domain append and final SUCCEEDED audit are separate obligations. SQL append
failure rolls all domain rows back but leaves a failed scoped job. Committed content
without original final success is unreadable and cannot be adopted. No audit deletion,
new pins, actor, clock or automatic cleanup heals an original obligation.

Current-source revalidation adds two complete present legacy SQL observations bracketed
by pinned Bronze reads. Changed current SQL need not invalidate unchanged original Bronze.
These observations are not atomic cross-resource snapshots, source-file hashes, original
plugin/decision replay or authenticated clocks. Public reader enforces readonly mode;
source/target live-file aliases reject while parent owners remain usable. Close writers
before readonly reopen. New SQL/tests quote actual catalog.schema.table identifiers.

## Independent resource contract

Prior profiles and accepted limits remain unchanged.

- 1..1000 whole-table rows; count preflight and max+1 transfer guard.
- Each stored text/JSON cell <=65536 UTF-8 bytes, independently of nullability.
- Aggregate transferred text <=1048576 bytes, including all non-null text/JSON cells.
- Complete canonical snapshot <=1048576 bytes, independently of raw SQL text size.
- Each full projected row <=524288 bytes; aggregate projections <=4194304 bytes.
  Escaping can exhaust this even if the original snapshot fits; reject BEFORE append.
- Bounded native envelope/metadata transfers, guarded IDs and original query row limits.
- Decoder raw bytes bounded before hashing/parsing; outer structure/key replay exact.

These bounds are not scan-cost/process-memory/hostile-file safety promises. No automatic
limit growth, filtered-view impersonation, partial success, approximation or unbounded export.

## Tests and honest verification

The pure suite exercises exact null/text/UTC/key/outer structure behavior and distinguishes
pure opaque-content consistency from actual JSON-column attestation. Native tests use
actual initialized DuckDBStore DDL plus explicitly seeded synthetic SQL, then actual
AuditLedger/BronzeEventStore and new producer/read/current-source paths. They cover nullable
symbol, SQL NULL versus JSON null, duplicate-key payload text as retained by SQL, exact
source SQL reconciliation, schema/view/key/count refusal, recording tampering, first-write,
extra jobs, actual failed append boundary, final audit, timezones, aliases and resources.

The fixtures do NOT invoke an unretrieved writer or assert its upsert/JSON conversions.
Boundary SQL seeding and failing SQL proxies are explicitly labeled, not fabricated
successful source evidence. No native strategy, authorization, broker/execution or
original decision replay is claimed. Persisted evidence-snapshot Silver is NOT included
in this Bronze package and is a subsequent source-linked migration step.

Assistant pure/isolated checks, if performed, are separately attributed in final delivery.
Syntax/line lengths/whitespace and ZIP exact unique members/nonempty/CRC/payload equality
are checked before delivery. They are not repository/Windows/uv evidence, Ruff, mypy,
full/native pytest or platform acceptance. Previous user-confirmed QA through f239b89
remains closed; delivery-time gaps do not reopen that QA.

Copy absent additions only; STOP/compare if any destination exists. No accepted source/QA
repair, pyproject/lock, logs/live_status.json or scripts/qa is replaced. No PowerShell QA
runner, per-payload SHA256 manifest or standalone verifier is included. Distributed pytest
work remains untouched and no full-suite parallel safety/speedup is certified.

New-work repository checks:

    uv run python -c "import sys; print(sys.executable); print(sys.version)"
    uv run pytest tests/data_platform/test_legacy_evidence_snapshots.py -q
    uv run pytest tests/data_platform/test_legacy_evidence_snapshot_bronze.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Check untracked additions for whitespace too. Real-data loading/migration, production
publication, authority/identity/key/policy registration, trading and cutover remain HELD.
Package QA is not platform acceptance or permission to release any hold.
