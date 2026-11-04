# Partitioned native legacy-market capture @1

## Reconciliation and why this next chunk

User reports 3539 passed, 2 warnings and QA passed. Accepted as user-confirmed
repository evidence, not assistant-reproduced QA. Warning contents were not supplied
and are not declared resolved. Reported HEAD/origin feat/medallion-feature-store:
5376f60 (Bronze legacy preservation), preceded by 75a5d71 (documentation).
Only short hashes were supplied; no full hash, independently inspected HEAD or
commit association for subsequent Silver/test repairs is invented.

Current Sources legacy_market_snapshot.py, BronzeEventStore and AuditLedger were
retrieved and inspected. The latest Silver dependency retrieval returned unrelated
files and one tool error. That is a retrieval limitation, not absence or stale user
work. The QA-accepted Silver/input/risk implementations and their fixes are untouched.

The actual snapshot@1 whole-table profile refuses above 1000 rows. This new profile
adds bounded partitioned WHOLE-TABLE capture and native audited coverage, without
raising that old limit, faking smaller source views or constructing partial @1
snapshots. It is an actual producer/consumer addition, not a workspace adapter,
inspection CLI, generic archive wrapper or research calculation.

## New contracts; no silent cross-profile compatibility

Format: legacy-market-partitions@1. Native source: legacy_market_partition_capture.
Every partition and its coverage manifest use this NEW version. Existing snapshot
and Silver readers are NOT rewired to consume it. This delivery does not persist
partitioned Silver or build Gold, publication or native decision inputs. A separate
reviewed partition-aware Silver contract remains necessary before that progression.

Selected table: entire main.option_stream or main.spot_candles under exact existing
native schema. Exact source label is explicit caller-reviewed metadata, not canonical
instrument identity, independent authority, globally unique namespace or file hash.
Native capture reuses inspected native snapshot schema/scalar encoding helpers and
requires its exact version and key contracts. No accepted dependency is included,
rewritten, downgraded or replaced by a successful-result substitute.

## APIs

legacy_market_partitions.py:

    capture_partitioned_legacy_table(readonly_source, table=..., source_label=...)
    make_partition_capture(table=..., source_label=..., schema=..., rows=...)
    replay_partition_capture(artifact, expected_capture_id=...)

make/replay are pure exact-content operations, not source attestation. The pure
schema is retained caller-supplied metadata; native capture alone enforces the
supported actual table/schema/cell contracts. Do not treat pure construction as
market-validity or original source verification.

legacy_market_partitions_store.py:

    preserve_partitioned_legacy_table(source, initialized_bronze,
        table=..., source_label=..., expected_capture_id=..., imported_at=...,
        actor_id=..., code_revision=...)
    read_partitioned_legacy_recording(readonly_bronze, capture_id=..., table=...,
        source_label=..., expected_recording_fingerprint=...)
    revalidate_partitioned_legacy_recording(readonly_source, readonly_bronze,
        capture_id=..., table=..., source_label=..., expected_recording_fingerprint=...)

No CLI, initialization, migration-release boolean, force override or automatic
source opening. Caller owns file-backed/read-only source and separate dedicated
initialized native target, with no outer transactions or concurrent writers.
Explicit code_revision is a reviewed 40-character lower-hex revision; short reported
commit hashes must not be padded/substituted for that identifier.

## Exact bounded coverage

The actual source table is read inside ONE SQL transaction; no independent OFFSET
pages, multi-page timestamp inference or queries over temporary filtered views.
Reads stream in batches of 128, rejecting row/byte overflow before promoting output.
The LIMIT is max+1 to detect overflow, never to label a prefix as the whole table.
Base-table schema and oversized stored text are checked in that transaction.
SQL scans may still examine larger data; this is not a scan-cost/time/memory ceiling.

Original legacy storage keys are used without canonical identity claims:
- option_stream: run_id, stored ts, provider instrument_token.
- spot_candles: provider instrument_token, interval, stored ts.

Rows sort lexicographically by canonical ENCODED key bytes, not by numeric token or
economic time. NULL keys and duplicate keys reject the entire capture, even if two
rows are numerically equal. No winner, omission, latest-good selection or salvage.
Partitions split deterministically on row count or encoded bytes. Each has an exact
index, contiguous first ordinal, inclusive lower/upper stored key and complete rows.
Manifest binds all payload hashes/byte counts, complete partition sequence, row
count and whole ordered row-sequence hash. These bounds prove reconciliation within
the captured selected SQL snapshot, not complete historical/provider truth.

Missing, reordered, repeated, altered, overlapping or gapped retained partitions
fail full canonical reconstruction. Recomputing outer hashes does not bypass the
manifest/row/boundary equality checks. An offline caller can construct a different
self-consistent set; content hashes are not authenticity or independent source proof.

Stored scalar encodings are inherited from the accepted native profile: exact
finite binary64 HEX (including signed zero), canonical integers, original stored
JSON text, DATE and UTC-normalized TIMESTAMPTZ instants. NULL remains NULL, zero stays
zero, unknown provider receipt/identity/times remain unknown. IV/Greeks present in
legacy option rows are retained legacy-derived values, not native recomputation.
Original physical SQL row order and original timestamp-offset spelling are not
claimed. Import serialization does not recover original provider HTTP/WS bytes.

## Bounds

- New profile: <=16 partitions, <=1000 rows and <=1 MiB encoded payload per partition.
- <=16000 total retained rows and <=4 MiB aggregate canonical row bytes.
- <=64 KiB per stored text cell; <=64 KiB coverage manifest.
- <=16 MiB complete retained artifact (manifest + complete partition bytes in hex).
- Exactly one manifest event plus every partition event in a single native batch.

These are independent refusal gates; not every input below one limit fits all the
others. Metadata overhead and long stored keys can require whole-capture refusal.
The 4096-byte split reserve is conservative, not a promise of optimal packing.
No changes to snapshot@1's 1000-row/1-MiB bound or existing Silver bounds.
This remains bounded migration capability, not unlimited production-scale migration.

## Native first-write recording

The producer freshly captures and fully compares the selected table twice; both
must match the explicit reviewed capture ID. Native Bronze append_batch retains
manifest + all partition events + complete input artifact in one domain transaction.
Every event is legacy_snapshot, not live_provider. imported_at is the import receipt
clock, not source availability/economic time. exchange/provider identity fields are
not fabricated. No domain publication/eligibility is asserted.

Scope binds version/table/label/capture ID. Earlier scoped jobs, batches, variants or
orphan artifact prevent adoption/retry before source capture. No repair, cleanup,
supersession or fingerprint-refresh API. A different reviewed capture is a distinct
scope, not a healing of an old failed obligation. Target is single-owner; preflight
checks are not a concurrent-writer locking protocol.

Domain commit and terminal audit commit remain separate. Final audit failure can
leave complete native domain data with RUNNING audit; readers reject it and no retry
adopts it. No partial partition batch is accepted as a complete capture.

The reader requires capture ID, exact subject and reviewed recording fingerprint.
It replays the FULL artifact, verifies all manifest/part payloads and complete
native envelopes, rejects multiple variants, checks original artifact/batch/job links,
all scoped job coverage and exact PLANNED/RUNNING/SUCCEEDED history, then binds all
recording metadata/clocks/ingest ordinals in the recording fingerprint. All SQL
catalog/schema/object names in new code/tests are fully quoted, including the
bronze.duckdb catalog/schema collision fixture. No fixture renaming workaround.

Native full-recording checks inherit the underlying source/storage assumptions.
Privileged SQL deletion/mutation or whole-file rollback is not prevented; fingerprints
are not authenticated build attestation, issuer authority or canonical identity.

## Retained recording versus current source

read_partitioned_legacy_recording validates original native preservation only;
current_legacy_source_checked=false. It can remain valid when the old SQL source
later changes. It does not relabel original evidence as currently complete.

revalidate_partitioned_legacy_recording validates the original recording, performs
two fresh whole-table SQL captures and requires complete equality, then rechecks
the native recording. Only this result sets current_legacy_source_checked=true.
It never refreshes pins or adopts later-good data. Sequential checks are not a
cross-database atomic barrier; changes after final observation remain possible.
Operational SQL/IO errors propagate, not manufactured policy or market outcomes.

## Verification attribution

Assistant sandbox: Python 3.12.8, DuckDB 1.2.2 installed.
25 pure partition/coverage tests PASSED. Includes 1/1000/1001/16000 rows, row and
byte-driven splitting, exact retained values, order invariance, duplicate/unknown
keys, actual aggregate/manifest byte bounds, missing/reordered/duplicate payloads,
wrong reviewed pins and rehashed schema/ordinal/boundary/content/JSON tampering.
No successful native dependency was mocked, cloned or substituted for these checks;
they are pure tests, NOT source SQL capture or native persistence E2E.

16 actual native integration cases are supplied for repository QA, NOT run here.
They reuse accepted actual synthetic legacy fixtures and actual native Bronze/audit
APIs, covering both table profiles, >1000-row whole coverage with old @1 still
refusing, before-read first-write refusal, failed original review, missing parts,
payload/artifact/batch/audit corruption, final-audit failure, real domain SQL failure,
recording/current-source separation, actual current-source revalidation, timezone
metadata equality and same-live-file cursor alias refusal with parent usability.
Fault injection changes an actual audit transition to raise only; no native successful
source or computed result is replaced. SQL test parameters all have short IDs.

Syntax, 100-column bounds, whitespace and ZIP CRC/exact members/payload hashes checked.
No repository/filesystem connector was available on discovery. Full pytest suites,
Ruff, mypy, Windows CPython3.14.2, DuckDB1.5.6 and Git diff/application NOT executed
by assistant. User's prior 3539-pass QA is accepted baseline, not this package's QA.

Review/copy ABSENT additions only, stop/compare if destinations exist. Run:

    uv run pytest tests/data_platform/test_legacy_market_partitions.py tests/data_platform/test_legacy_market_partitions_native.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Check untracked whitespace separately. No scripts/qa runner, manifest or standalone
ZIP verifier is added. Do not auto-stage, clean or discard logs/live_status.json.

Real user-data loading/migration/backfill, live acquisition, actual trust/identity
registrations, publication, trading and decision-loop cutover remain HELD.
Disposable synthetic fixtures only. Package QA is not whole-platform acceptance.
