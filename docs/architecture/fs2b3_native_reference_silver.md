# FS2b3: native HTTP receipt decoding and Silver reference assessments

## Actual baseline and delivery boundary

Inspected Project Files confirm kite-instrument-http@2, strict Transfer-Encoding
comparison, parser-mode guard, DEFAULT_HTTP_POLICY singleton, native body/metadata
pair storage, A1 lifecycle and existing Silver conventions. Do not overwrite these.
Targeted searches did not return FS2b1 instrument_reference modules. This package is
additive and does not claim integration with unseen code or substitute an old copy.

A distinct versioned native CSV contract is deliberate, not a legacy compatibility
wrapper. FS2b1 offline snapshots and native HTTP observations are not silently unified.
A later reviewed consolidation may reuse validators after actual source reconciliation;
no stored parser version may change meaning. No instrument cache, IV/Greeks, strategy,
eligibility, decision-loop or native acquisition modification. No broker operations.

## Contracts and evidence

- Content decoder: kite-reference-content@1.
- Native CSV: kite-native-reference-csv@1.
- Normalizer: kite-native-http-reference@1.
- Evidence gate: version 1, native capture policy @2 / metadata schema 1 only.
- Command: normalize.kite_native_reference@1.
- Dataset: silver.kite_http_reference_results, schema/contract 1, append revisions.

Authoritative references reviewed:
https://kite.trade/docs/connect/v3/market-quotes/
https://docs.python.org/3/library/zlib.html

Kite's CSV documentation explicitly shows blank strike for equities/futures; keep
missing values, not fabricated zero. name is a company/provider field, not an inferred
underlying. last_price in the daily dump is not realtime. Tokens may be reused after
expiry; none of these rows represents timeless canonical identity.

## Verification before content decoding or quality filtering

Caller supplies FOUR exact pins: body capture_event_id/envelope_hash and metadata
capture_event_id/envelope_hash. Use a read-only Bronze connection and a separate,
single-owner dedicated Silver DB. Source verification runs in one Bronze read transaction.
Fully qualified quoted catalog.schema.object names handle bronze.duckdb/silver.duckdb.

1. Check both receipt identities for conflict variants before selecting a candidate.
   Lists are bounded at 33 with an explicit limit-reached flag; any multiplicity rejects.
2. Bound BLOB/envelope reads in SQL. Recheck payload, envelope and receipt-identity hashes,
   canonical envelope fields, native origin, duplicated receipt/source/format fields.
3. Require body and metadata record roles, same source/session/first batch/job. Verify
   committed FS1a batch fingerprint, exact two-event ordering, input hash, conflict count,
   and exact stored input artifact bytes. No missing artifact is manufactured.
4. Verify acquisition command, latest event index/state, scope and capture-policy config
   fingerprint. Only SUCCEEDED permits decoding. Failed, running or incomplete capture
   audit is an explicit quarantine, not a repaired source audit state.
5. Validate native @2 metadata, endpoint, body hashes/length, explicit completeness,
   framing, policy limits and actual aware receipt clocks. Reject foreign headers,
   legacy/offline origins, @1 and unsupported versions, prefixes and publication assertions.

Malformed/missing/conflicting evidence yields a persisted explicit quarantine when
inspection can complete. Infrastructure/SQL errors fail the normalization job, rather
than inventing a disposition from evidence that could not be inspected. No metadata or
body exceptions are logged verbatim. No raw/account JSON is emitted in diagnostics.

Gate success is an observed evidence state, not a perpetual entitlement. Later appended
conflicts can change it. It is NOT enough for a future consumer to reuse an old normalized
row merely because a prior audit succeeded.

## Pure bounded content and CSV policies

Encoded input <=8 MiB; decoded output <=16 MiB. Identity (including missing Content-Encoding)
and a SINGLE gzip member supported. Duplicate encoding/type headers, stacked/unknown
encodings and unsupported media/charset quarantine. No magic gzip sniffing. Media allowlist:
text/csv, application/csv, text/plain, application/octet-stream; optional charset UTF-8,
UTF8 or US-ASCII. Decoder owns Content-Encoding whitespace interpretation explicitly;
it never relies on a transport parser to remove content coding.

Use zlib.decompressobj with gzip header/trailer validation and max_length=limit+1.
Never call unbounded flush. Require eof, valid checksum and no unused_data; reject
truncated streams, CRC errors, trailing padding/data and concatenated members. No gzip
or CSV prefix salvage; no partially normalized rows. These single-member/trailing-data
rules are versioned platform policies, not a claim that all such gzip files are invalid.

CSV: strict UTF-8 with optional BOM; exact ordered documented columns, header whitespace
stripped only. <=200000 records; each field <=4096 characters. csv.reader's own field
limit may produce MALFORMED_CSV before the explicit field-size check. Reject unknown
column layouts, invalid dates/integer ranges and malformed CSV as a whole.

Keep exact validated decimal strings (max64 characters), without float conversion.
Blank last_price/strike/tick_size => null. Zero remains zero. No exponent/negative or
nonfinite decimal notation in v1. Provider token is positive uint32; exchange token
validated numeric string; lot_size nonnegative int64 is an observation, not eligibility.
CE/PE require expiry and strike; FUT requires expiry but may have no strike. Other
nonempty provider types remain provider labels, not inferred contract classes.

Row ordinal is zero-based CSV DATA RECORD ordinal, not physical line/byte offset.
Each source_fields_hash hashes parsed field strings, not original CSV byte slices.
Exact source bytes remain in Bronze. Duplicates are preserved, not first/last-wins.
No canonical contract ID, underlying guess or historical token resolution is created.

## Append-only assessments and idempotency

input_revision_id hashes four pins plus normalizer/content/CSV versions. The full
normalization input also includes the observed gate evidence snapshot. revision_id
hashes input_revision_id plus gate_fingerprint. Thus identical pins/versions/GATE STATE
are idempotent; a later appended conflict or audit completion creates a distinct immutable
assessment rather than changing a row or disguising changing evidence as deterministic.
No observed-at clock enters the gate fingerprint, so ordinary retries do not duplicate.

Deterministic output/evidence/source clocks must match on exact retry or fail closed.
New normalizer/decoder/CSV versions coexist. Each new assessment records supersedes_json
for earlier assessments of the SAME input_revision_id, including quarantine assessments.
A history cap of 1000 fails closed rather than silently truncating supersession links.

This is an assessment ledger, not a "latest good row" selector. Future consumers MUST
resolve supersession/invalidation and fresh source gate state BEFORE quality filtering;
otherwise an earlier normalized value can resurrect after a later quarantine. There is
no publication/quality-filtered read API in this package and no automatic cross-version
winner selection. Immutable older normalized rows are retained as historical evidence.

Rows are typed frozen records serialized in result_json, not a finalized relational
instrument master. decoded_payload_hash is a derivative-byte hash, not a new Bronze
original. No offline re-import/relabel shortcut and no UPDATE/REPLACE in domain writers.

## Clocks, audit and replay

Preserve source request/header/first-chunk/capture-end clocks and separate body/metadata
Bronze receipt and recording clocks in source_times_json. Missing/unverifiable clocks
stay absent in quarantines; never substitute normalization time. normalized_at and
recorded_at are actual local clocks, not commit/publication times. published_at,
provider_published_at, effective_from/effective_to remain null. No HTTP Date inference.
No exact_decision_replay/as_known_at/research_recomputed publication semantics are
claimed. Those require subsequent pinned published reference bundles and validity/
identity assertions, with research recomputations explicitly labelled.

A1 audits every normalization run, including exact retries and expected quarantine.
Expected quarantine is a successful classification job; it is NOT published success.
Unexpected failures roll back the result insert and fail A1. Explicit initialization
bootstraps A1 and creates Silver objects within the job, following the existing pattern.
Domain commit and A1 finalization remain separate; unfinished audit after committed
rows is possible and must not be manufactured successful. Plan never opens a DB.

## Validation limits

VALIDATION.txt distinguishes pure tests, isolated real-DuckDB SQL/evidence tests with
ledger/contract doubles, and SUPPLIED real A1/FS1a/FS2b2 integration tests. The doubles
are not evidence of real A1 integration or contract registration. No current local
branch/HEAD or full QA verification, live broker tests, throughput, losslessness,
process-crash recovery or production-readiness certification is implied.

Test fixtures deliberately corrupt source tables to exercise integrity rejection;
production readers/writers never perform those fixture mutations.
