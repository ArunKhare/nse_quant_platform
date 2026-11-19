# Partition-aware persisted legacy Silver @1

## Delivery and scope

This additive package introduces `legacy-market-partition-silver@1`, command
`normalize.legacy_market_partition_silver@1` and DatasetContract
`silver.partition_legacy_observations`, version `1`.
It consumes actual native `legacy-market-partitions@1` recordings. It does not feed
partition payloads into snapshot@1 or Silver@1, change either older contract's limits,
replace accepted dependencies, extend the paper loop, recompute Gold, publish or admit decisions.

Files added:

- src/nse_quant/data_platform/legacy_market_partition_silver.py
- src/nse_quant/data_platform/legacy_market_partition_silver_store.py
- tests/data_platform/test_legacy_market_partition_silver.py
- tests/data_platform/test_legacy_market_partition_silver_native.py
- docs/LEGACY_MARKET_PARTITION_SILVER.md

Review/copy ABSENT additions only. If any destination exists, stop and compare;
this is not authorization to overwrite that file. No scripts/qa, PowerShell runner,
per-payload manifest, standalone verifier or replacement dependency is included.
No repository write, commit, push, real migration or initialization was performed.
Do not stage, discard, delete or clean logs/live_status.json.

## Inspected interfaces and status attribution

Current Sources returned the complete partition codec/store, Silver codec/store,
repaired pure and native Silver tests, partition native tests, AuditLedger,
BronzeEventStore, DatasetContract and partition documentation. They establish the
actual source reader signature, recording DTO, native fixture imports, audit state
transitions, domain/final-audit split and current scalar/materialization interfaces.
The oversized Silver parameter has explicit short IDs; current native Silver test
mutations/assertions retrieved include fully qualified names. Existing files are untouched.

A final targeted request for the four outputs inspection reports and the original
snapshot fixture returned the already-inspected partition/Silver modules instead.
Those reports and that fixture body were not independently retrieved in this turn;
this is a retrieval limitation, not evidence of missing or stale user files. New tests
import the actual existing partition producer helpers and their actual legacy fixture;
no successful source DTO, native reader, storage or audit replica is supplied.

User-confirmed baseline: Silver/fix QA reported 3539 passed, 2 warnings, QA passed.
Warnings were not described and are not declared resolved. Partition delivery occurred
later; no partition-specific user QA or actual partition commit hash was supplied.
Reported short hashes 5376f60 and 75a5d71 remain short; no later work is assigned to them.
This package has no independently inspected repository commit association.

## Native source boundary

`PartitionBronzePins(capture_id, table, source_label, recording_fingerprint)` requires
explicit exact subject plus reviewed content and recording pins. The producer calls
`read_partitioned_legacy_recording` itself repeatedly and compares complete returned
recordings and artifacts. No public persistence parameter accepts observations,
PartitionCapture or NativePartitionRecording as an already-successful native source.

The source reader verifies the original retained artifact, complete event/envelope
coverage, batch, original job/audit links and metadata fingerprint. The new codec also
replays the entire artifact, verifies exact native schema/subject, and validates every
stored scalar with the accepted legacy Silver scalar validator. Reuse is limited to
scalar validation and foundation SQL/path/metadata utilities, not snapshot projection.
Native dependencies must be installed from the actual current repository.

First-write scope binds this new version and capture/table/label, deliberately NOT
the recording fingerprint. Changing a recording pin cannot create a fresh scope for
the same capture. Prior sets, attempts or scoped jobs block before source reading;
orphan same-capture rows independently block adoption. Failed/planned/running/cancelled
or unlinked scoped obligations are not filtered away. No retry, repair, refresh,
latest-good selection, salvage or adoption API exists.

The producer assumes a single-owner dedicated target, no external transactions and
no concurrent writers. Preflight is not a multi-writer locking protocol. Sequential
source observations are not an atomic cross-database snapshot and cannot rule out
changes after the last observation.

## Stored coverage and lineage

A dedicated initialized file-backed Silver database has four new Silver tables:
partition_legacy_versions, partition_legacy_sets, partition_legacy_observations and
partition_legacy_attempts, plus the actual native audit ledger tables. Initialization
is explicit and refuses existing tables; this does not adopt an old Silver database.
All new domain SQL uses quoted actual catalog/schema/table names. Tests deliberately
retain silver.duckdb and bronze.duckdb catalog/schema collisions.

The set retains exact source pins and the complete bounded partition artifact, not
only a claimed hash. The reviewed Bronze recording fingerprint binds the actual
original Bronze metadata observed at creation; retained Silver replay does NOT
independently re-attest that metadata without Bronze. Privileged whole-file rewriting
or rollback is not prevented by hashes or application audit APIs.

Every row persists and rechecks:

- Full canonical record bytes and record ID.
- Capture ID, exact subject and reviewed recording fingerprint in source pins.
- Partition index, payload hash and partition-local ordinal.
- Contiguous global source ordinal and native partition source event ID.
- Inclusive partition key bounds and first ordinal in exact record bytes.
- Every stored field, stored legacy key and separately classified legacy-derived fields.
- Materialized token, aware stored timestamp, volume and OI, distinct NULL versus zero.

Full canonical partition replay recomputes deterministic splitting, ordered keys,
manifest counts, ordered row-sequence hash, payload hashes, byte counts and boundaries.
Missing/repeated/reordered/gapped/overlapping/mixed or altered parts refuse as a whole.
Silver replay derives every expected record again, compares complete SQL row tuples
and complete bytes, and recomputes revision ID. Same-capture rows under another
revision are included in coverage preflight rather than hidden by a good-subset filter.
Original set/attempt/job/history links and exact PLANNED/RUNNING/SUCCEEDED history
must agree. The separately reviewed Silver recording fingerprint also binds clocks,
links, indices, source pins and original recording metadata.

Set, every row and attempt link commit in one domain transaction. Final audit commits
separately. A failed row insertion rolls back that domain transaction but retains the
failed job. Final-audit failure may leave all domain rows with RUNNING audit; reads
reject them and retry cannot heal/adopt them. Operational SQL/IO failures propagate.

## Bounds and value semantics

All source partition bounds remain unchanged: at most 16 partitions, 1000 rows and
1 MiB per partition, 16000 rows total, 4 MiB aggregate canonical source row bytes,
64 KiB text cells/manifest, 16 MiB complete source artifact. Source bounds apply
independently; being below one does not imply acceptance under the others.

This NEW Silver profile independently permits at most 512 KiB per projected record
and 32 MiB aggregate projected record bytes, with at most the original 16 MiB source
artifact. This is not an increase to Silver@1's 8 MiB/1000-row bounds. A valid source
capture may still fail the new projection budget; no partial Silver set is accepted.
Repeated lineage/key-bound metadata counts toward the projection budget. Aggregate
SQL row-count/byte preflight occurs before BLOB transfer, with per-record and context
CASE guards. These gates are transfer/content bounds, not SQL scan-cost or peak-memory
ceilings; canonical replay intentionally materializes bounded collections.

Finite binary64 HEX, including signed zero, is exact stored binary64, not recovered
original decimal price spelling. JSON remains exact stored text. Canonical integer,
DATE and UTC-normalized stored TIMESTAMPTZ rules are reused. Naive timestamps are
rejected, not relabeled UTC. NULL/zero remain distinct. IV/Greeks remain legacy-derived,
not native recomputation. Import clocks are not original provider receipt/availability.

Every record remains RETAINED_LEGACY_OBSERVATION_NOT_MARKET_VALIDATED. Canonical
contract identity stays null; original-provider-bytes, identity, availability,
economic-validity, publication and decision-eligibility assertions remain false.
Unknown independent original artifacts elsewhere remain unknown. No complete historical
versions are recovered from INSERT OR REPLACE retained tables.

## APIs and three distinct checks

Codec:

    PartitionBronzePins(capture_id, table, source_label, recording_fingerprint)
    derive_partition_records(complete_artifact, pins=...) -> tuple[bytes, ...]
    record_values(record_bytes) -> tuple[object, ...]

Pure derivation validates content, never source attestation.

Store:

    initialize_partition_silver(empty_file_backed_target)
    persist_partition_silver(readonly_bronze, initialized_target,
        pins=..., actor_id=..., code_revision=...)
    read_partition_silver(readonly_silver,
        revision_id=..., expected_recording_fingerprint=...)
    revalidate_partition_silver(readonly_bronze, readonly_silver,
        revision_id=..., expected_recording_fingerprint=...)
    revalidate_partition_silver_source(readonly_legacy, readonly_bronze, readonly_silver,
        revision_id=..., expected_recording_fingerprint=...)

The producer returns revision_id, recording_fingerprint, row_count, job_id and a false
eligibility assertion. Code revision must be an explicitly supplied real reviewed
40-character lower-hex identifier; reported short commit hashes must not be padded.
Caller owns connections and closes writer owners before reopening files read-only.
Same-live-file cursor aliases refuse without closing or damaging the parent handle.

1. read_partition_silver checks retained Silver recording and full recomputation only.
2. revalidate_partition_silver additionally invokes the actual current native Bronze
   reader repeatedly with original pins; it does not read the current legacy database.
3. revalidate_partition_silver_source additionally invokes the actual partition source
   revalidator, including two fresh whole-table legacy SQL captures, then rechecks
   Silver/Bronze. It never refreshes original pins or claims independent time truth.

Changing the old SQL source can leave retained Silver and Bronze checks valid while
current-source validation fails. Later Bronze corruption can leave retained Silver
replay valid while current-Bronze validation fails. None is interchangeable with
independent provider truth, publication admission or native decision replay.

## Tests supplied and verification actually performed

Supplied: 23 pure test cases and 34 actual native integration cases (parameter-expanded
counts inspected from AST, not pytest collection). Native tests reuse existing actual
synthetic legacy/partition producer fixtures, BronzeEventStore and AuditLedger. They
cover both source tables, 1001 rows/two partitions, all three read modes, exact values,
lineage/scalar/byte corruption, missing partitions, original contract/audit/attempt
coverage, unlinked scoped jobs, failed source observations, metadata drift, partial
row-preparation rollback, actual SQL domain failure, final-audit failure, orphan rows,
extra same-capture revisions, aggregate/per-row transfer bounds, timezone, readonly
requirements, aliases and operational errors. Failure injections only raise; no
successful native lower-boundary result is substituted. Pure cases include 16000-row
coverage, source bound preservation, rehashed incomplete/mixed manifests and malformed
stored cells and a real aggregate projection overflow from repeated boundary lineage.
Every parametrization has short explicit IDs.

Assistant-executed in sandbox Python 3.12.8 / DuckDB 1.2.2:

- Syntax compilation of the four NEW Python files, line-length/whitespace checks.
- Isolated execution of the exact NEW record_values function and exact NEW SQL CREATE
  TABLE expressions (AST-extracted, not imported native pipeline): 15-column insert,
  aware-timezone equality, NULL/zero retention, primary-key rejection and rollback.
- Disposable silver.duckdb catalog/schema-collision SQL check with exact new DDL,
  partial-domain constraint failure/rollback, writer close and readonly reopen with
  timezone/full-row equality. These are isolated actual SQL/filesystem checks only.
- ZIP unique exact members, nonempty payloads, CRC and byte-for-byte payload equality.

NOT run: the 23 pure tests with actual repository imports; the 34 native tests; focused,
platform or full repository pytest; Ruff; mypy; uv-selected Windows Python 3.14.2 /
DuckDB 1.5.6; Git diff/application. Ruff is unavailable in this sandbox. Source text
retrieval is not an executable checkout; accepted dependency modules were not rebuilt
as sandbox substitutes. Isolated AST/SQL checks are NOT native E2E or repository QA.

## Local synthetic QA, not a migration command

No QA runner is supplied. After reviewing absent additions, the requested checks are:

    uv run python -c "import sys; print(sys.executable); print(sys.version)"
    uv run pytest tests/data_platform/test_legacy_market_partition_silver.py tests/data_platform/test_legacy_market_partition_silver_native.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Also inspect whitespace for untracked additions; git diff does not cover them.
Prior QA remains accepted, but does not establish this new package's QA. Do not
attribute a future pass or commit until actual results are supplied.

## Execution and eligibility holds

REAL DATA LOADING/MIGRATION HOLD REMAINS. No live acquisition, user-data loading,
backfill, real identity/key/policy registration, production publication, trading or
native decision-loop cutover is authorized. Only disposable synthetic fixtures are
within this package's QA scope. This delivery adds no trust root, authority,
force-eligible flag, eligibility contract, Gold build or positive strategy lane.
Package correctness/QA does not establish whole-platform acceptance.
