# Native migrated legacy price Gold @1

## Delivery, baseline and holds

New store profile: legacy-market-price-gold@1.
Feature version: legacy-stored-price-geometry@1.
Command: build.legacy_market_price_geometry@1.
DatasetContract: gold.legacy_price_features / 1 / VERSIONED_BUILDS.

User reports local HEAD 952cb21 on feat/medallion-feature-store for partition-aware
Silver, origin/feat/medallion-feature-store at 64caedb for partitioned capture, and
QA/tests passed. These are user-confirmed short identifiers and QA, not independently
inspected Git, full hashes or assistant execution. No push/current clean-worktree
claim is made. Earlier baseline warnings were unspecified, not declared resolved.
The older delivery documents' unconfirmed statuses are historical, not a reason to
reopen your now-confirmed package QA. This new Gold package still requires its own QA.

REAL-DATA LOADING/MIGRATION HOLD REMAINS. No live acquisition, user-data loading,
backfill, actual identity/key/policy registration, production publication, trading
or decision-loop cutover is authorized. Disposable synthetic fixtures only. No
independent authority, identity, historical availability or economic validity is
invented. Package QA is not whole-platform acceptance.

This is a first migrated-data Gold feature family, NOT the complete Gold analytics
suite, publication/admission contract or native decision loop. The legacy paper
consumer is untouched. Research IV/BSM/stress implementations are not rebuilt.

## What this chunk implements

Actual synthetic legacy SQL -> native partition Bronze -> persisted partition Silver
-> repeated actual native Bronze/Silver revalidation -> exact price-geometry
recomputation -> audited persisted Gold build, every input and every output row
-> retained replay / separately requested current-native-source revalidation.

The current partition-Silver codec/store and native tests were retrieved after an
exact-path retry. Initial retrieval returned older related modules; this was a
retrieval limitation, not evidence of stale/missing user work. Current formatting
and native reader signatures were inspected; accepted files are not replaced.
DatasetContract and AuditLedger interfaces were also retrieved and inspected.
The current quote-Gold family was inspected for native contract context; it is NOT
misused as a migrated legacy source or rewritten by this addition.

Files added, and only these:

- src/nse_quant/data_platform/legacy_market_gold_features.py
- src/nse_quant/data_platform/legacy_market_gold.py
- src/nse_quant/data_platform/legacy_market_gold_store.py
- tests/data_platform/test_legacy_market_gold_features.py
- tests/data_platform/test_legacy_market_gold_native.py
- docs/LEGACY_MARKET_PRICE_GOLD.md

Review/copy ABSENT additions only; stop and compare if a destination already exists.
No scripts/qa, PowerShell QA runner, per-payload manifest or standalone verifier.
No existing source/test dependency or runtime log is included as a replacement.
Preserve logs/live_status.json. No repository writes, staging, cleanup, commits,
pushes, real-data initialization or migration were performed by the assistant.

## Research feature definitions

All arithmetic uses Fraction over exact retained finite binary64 values. Results
are reduced rational numerator/denominator integer strings, with positive denominator.
This avoids floating intermediate overflow and underflow; it does not recover
original provider decimal prices, tick size, currency, exchange validity or accuracy.
Arithmetic zero normalizes to 0/1; signed zero remains distinguishable in retained
source bytes, not in the rational output.

For each spot_candles row:

- high_minus_low = stored high - stored low.
- close_minus_open = stored close - stored open.
- upper_shadow = stored high - max(stored open, stored close).
- lower_shadow = min(stored open, stored close) - stored low.

For each option_stream row:

- ask_minus_bid = stored ask - stored bid.
- bid_ask_midpoint = (stored bid + stored ask) / 2.
- ltp_minus_midpoint = stored LTP - that arithmetic midpoint.
- spot_minus_strike = stored spot - stored strike.

The midpoint is only arithmetic on the stored columns. This does not promote those
legacy columns to authenticated order-book/depth semantics or assume synchronous
observations. spot_minus_strike is a signed difference, not normalized moneyness,
option intrinsic value, an expiry/settlement claim or canonical underlying binding.
No annualization, rates, dividend yield, option expiry clock or exercise-style
assumption is introduced. No BSM/IV/Greeks/RV recomputation is claimed here.

Missing required operands produce an explicit UNAVAILABLE status with null numerator
and denominator. Zero remains computed zero. Negative inputs, zero inputs, inverted
high/low, open/close outside the stored range, crossed stored bid/ask and LTP outside
the stored bid/ask are flagged in fixed deterministic order. No clipping, winner,
repair, skipped row or market approval occurs. Inconsistent finite values can yield
negative geometric quantities; that is retained arithmetic with flags, not validity.

Legacy IV/Greeks are retained under retained_legacy_derived_fields, separate from
native_recomputed_features. They are NOT relabeled recomputation or used to compute
this profile. Full source bytes also retain all other fields, NULL/zero distinctions,
JSON text and signed-zero encodings.

## Native source and complete coverage

GoldSourcePins(revision_id, recording_fingerprint) requires an exact reviewed native
partition-Silver revision and its separately reviewed recording fingerprint. The
producer has no successful-source-DTO, computed-feature or caller-verified override.
It calls the ACTUAL revalidate_partition_silver repeatedly. That reader verifies the
retained Silver recording and current native Bronze with original pins. The producer
compares full source rows before committing. This does not read current legacy SQL;
Silver's separate current-legacy-source API remains available for explicit upstream
checks but is not silently asserted by Gold.

Pure content replay additionally reconstructs a complete partition capture from all
retained Silver fields using actual existing schema/codec APIs, requires the original
capture ID, rederives every Silver record and compares the FULL bytes/sequence. It
therefore rejects missing, duplicate, reordered, mixed or altered source lineage,
including promoted flags, not merely changes to selected price fields. This is
content reconciliation, NOT a new attestation of original Silver audit metadata.
Only the actual source reader establishes that original recording at production or
current-upstream revalidation. An offline caller can construct self-consistent pure
content; pure construction is never native provenance or decision eligibility.

Exactly one output row exists for every input ordinal. Each Gold record binds:

- Reviewed Silver pins and exact source record hash.
- Original Bronze pins, capture/table/label, partition hash/index/local ordinal,
  global ordinal, native source event ID and retained stored key.
- Provider token, stored source timestamp, feature version, exact new rational
  features, explicit availability statuses and quality flags.
- Separately retained legacy-derived fields and explicit research-only classification.

All rows retain canonical_contract_id=null, independent availability/economic validity
false, published_at=null, publication_asserted=false and decision eligibility=false.
SQL event_ts is explicitly the legacy stored timestamp, NOT independent provider
exchange time/receipt, original availability or knowledge_cutoff. No naive timestamp
is assigned UTC. Original provider bytes and overwritten legacy versions are not
reconstructed. Unknown independent artifacts elsewhere remain unknown.

## Native storage, first write and failure behavior

A separate, dedicated initialized file-backed database owns five Gold tables:
legacy_price_versions, legacy_price_builds, legacy_price_inputs,
legacy_price_features and legacy_price_attempts, plus the actual four audit tables.
The initializer refuses preexisting tables. Interrupted initialization is not adopted.
All new domain SQL fully quotes actual catalog/schema/table names. Actual Gold tests
use gold.duckdb; upstream fixtures retain silver.duckdb/bronze.duckdb collisions.
No accepted collision/short-ID/fixture-owner repairs are replaced.

Scope binds store version and exact source Silver revision, NOT the recording pin
or runtime. Changing a pin/runtime cannot open a fresh adoptable scope after failure.
Original scoped jobs, attempts or builds refuse before source observation. Same-source
orphan input/feature rows separately refuse. No retry, adoption, repair, latest-good
selection, supersession or automatic recovery is supplied. A genuinely different
reviewed Silver revision is a different source, not healing an old obligation.

Build identity binds version/definition, exact source pins, observed Python/DuckDB
runtime versions and every source/feature row hash. The separately reviewed recording
fingerprint additionally binds original clocks, complete materialized indices,
original job, attempt links and exact PLANNED/RUNNING/SUCCEEDED history. Unlinked
scoped jobs in any state remain blockers rather than being filtered away.
Same-source rows under another build are included in count/byte/row reconciliation;
a good build subset cannot hide orphan rows for that source.

Build + every source row + every feature row + attempt link commit atomically in
one domain transaction. Final audit success commits separately. Partial row/SQL
failure rolls back domain data while retaining the failed audit obligation. Final
success-audit failure can retain complete domain rows with RUNNING audit; readers
refuse them and retry cannot adopt them. SQL/IO errors propagate, never policy success.

Single-owner connections, no enclosing transactions or concurrent writers are
required. Sequential checks are not an atomic cross-resource barrier. No claims are
made about changes after final observation or multi-writer locking. Application audit
and fingerprints do not prevent privileged SQL mutation or whole-file rollback and
are not authenticated code/build/issuer attestation.

## Bounded replay and runtime

Independent unchanged source gates still apply: <=16 partitions, <=1000 rows and
1 MiB per partition, <=16000 rows total, <=4 MiB canonical source row bytes,
<=64 KiB text/manifest, <=16 MiB original artifact. Existing snapshot@1/Silver@1 and
partition-Silver limits are untouched.

This Gold profile adds independent limits:

- 1..16000 full Silver input rows.
- <=512 KiB per retained input and <=32 MiB aggregate retained input bytes.
- <=64 KiB per recomputed Gold row and <=32 MiB aggregate Gold row bytes.
- <=512-byte source-pin context; <=1024-byte runtime context on recording reads.
- Bounded dedicated metadata inventory and original audit row coverage.

Input and output byte gates apply independently; a valid source can still refuse
this profile. There is no partial success. Aggregate SQL count/byte preflight for
BOTH input and output tables occurs before their BLOB transfers. CASE guards also
limit each transferred row/context. Bounds are content/transfer gates, not SQL scan
cost, total process-memory or latency promises. Complete bounded collections are
intentionally materialized for deterministic replay.

Observed Python version and DuckDB distribution version are retained in runtime_pins.
This @1 reader deliberately requires exact current-version equality before replay;
there is no cross-runtime certification, portable-reader fallback or pin refresh.
The arithmetic is exact rational, but this profile conservatively pins its runtime.
The pins do not authenticate the installed interpreter, executable or source code.
A future cross-runtime/lifecycle profile requires separate review.

## APIs

Pure arithmetic, without native dependencies:

    price_geometry(stored_fields, table=...) -> features/statuses/quality flags

Gold codec (untrusted content only):

    GoldSourcePins(revision_id, recording_fingerprint)
    validate_source_records(complete_silver_records)
    derive_gold_records(complete_silver_records, pins=...)
    feature_values(exact_feature_bytes)

Native service:

    initialize_legacy_price_gold(empty_file_backed_target)
    persist_legacy_price_gold(readonly_bronze, readonly_silver, initialized_gold,
        pins=..., actor_id=..., code_revision=...)
    read_legacy_price_gold(readonly_gold,
        build_id=..., expected_recording_fingerprint=...)
    revalidate_legacy_price_gold(readonly_bronze, readonly_silver, readonly_gold,
        build_id=..., expected_recording_fingerprint=...)

Persistence returns build_id, recording_fingerprint, row_count, feature_version,
job_id, published=false and decision_eligibility_asserted=false. The code revision
must be an explicitly reviewed real 40-character lower-hex identifier; do not pad
the user-reported short commits. The caller owns handles and closes writers before
read-only reopen. Same-live-file cursor aliases refuse without damaging the parent.

read_legacy_price_gold performs complete retained input/content/feature/index/audit
replay and verifies the reviewed Gold recording fingerprint. It does not assert
current Bronze, current Silver, current legacy SQL, publication or market truth.
revalidate_legacy_price_gold additionally uses the actual current native upstream
reader and compares full recomputation, then rechecks Gold. A changed old SQL source
can leave these native checks valid; explicit current-SQL revalidation is separate.
Later native upstream corruption can leave retained Gold replay valid while current
native-source validation fails. None of these checks is independent economic truth.

## Tests and honest verification

Assistant sandbox Python 3.12.8: 27 tests of the actual new independent arithmetic
kernel PASSED. Includes both profiles, exact ratios, missing/zero/signed-zero cases,
canonical finite stored HEX, malformed/bounded cells, negative/inconsistent geometry,
subnormal midpoint below float representability and finite maximum midpoint without
intermediate float overflow. These tests are not native migration E2E.

Supplied: 44 additional repository-dependent integration/content cases, NOT run here.
They import current actual producer fixtures and actual native readers/ledger, not
successful native substitutes. Cases include 1001 rows/two partitions, both source
tables, all-source lineage, retained-IV separation, full byte/scalar/publication
corruption, original audit/attempt/contract/runtime obligations, unlinked scoped jobs,
pre-read first-write refusal, failed second actual source observation, partial-row
rollback, actual SQL domain failure, final-audit failure, metadata drift, orphan rows,
extra same-source build rows, both aggregate/per-row transfer guards, source recording
pins, timezone, clock-fingerprint drift, readonly/alias requirements and operational
SQL failures. Content-only cases additionally exercise 16000-row recomputation,
count/byte bounds before decode and rehashed/promoted/reordered source records. Do
not describe every case as full native E2E. Fault injections only raise; no successful
lower-native-boundary result is substituted. Parametrizations have short explicit IDs.

Assistant also executed isolated actual SQL/filesystem checks under DuckDB 1.2.2:
AST-extracted EXACT new five table DDL expressions and feature_values function,
12-column materialization, null publication, primary-key failure and partial-domain
rollback, gold.duckdb catalog/schema collision, writer close/read-only reopen and
Asia/Kolkata timestamp/full-row equality. Native dependencies were NOT reconstructed
to run these checks. They are isolated DDL/materialization checks, not native E2E.

All five new Python files were syntax-compiled and checked for <=100-column lines,
trailing whitespace and tabs. ZIP nonempty/unique exact members/CRC/payload equality
were checked internally. No per-payload manifest or verifier is delivered.

NOT run: the repository-dependent cases; uv-selected Windows Python3.14.2 / DuckDB1.5.6;
full platform/repository pytest; Ruff; mypy; Git diff/check/application. Ruff/mypy are
unavailable in this sandbox, and connector discovery found no repository/execution
connector. Source retrieval is not an executable Windows checkout.

After absent-addition review, synthetic local QA commands (no runner added):

    uv run python -c "import sys; print(sys.executable); print(sys.version)"
    uv run pytest tests/data_platform/test_legacy_market_gold_features.py tests/data_platform/test_legacy_market_gold_native.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Also check untracked additions for whitespace; Git diff does not cover them.
Your accepted prior QA is not reopened or treated as this package's QA.

## Remaining work

This does not deliver IV/RV migration contracts or native recomputation requiring
explicit time/rate/settlement/series assumptions, all remaining legacy table families,
production-scale paging/recovery, published bundles, decision admission, native
strategy/risk inputs or full platform acceptance. Future analytics must reuse actual
accepted native solver/domain contracts rather than legacy IV/Greeks or guessed
expiry clocks. Research-only publication, if later added, must preserve explicit
ineligibility and cannot become POINT_IN_TIME_DECISION by relabeling.
