# FS2b2: native Kite instrument-reference HTTP acquisition

## Delivery and boundary

Reconstructed from the implementation in this conversation, not a byte-for-byte
recovery of the previous unavailable archive. Existing project files are not replaced.
The available source inspection exposed A1/FS1a but not newly committed FS2a/FS2b1;
this package relies only on those inspected native audit/Bronze APIs. Local Windows
branch and HEAD have not been verified in the build environment.

Implements source acquisition into Bronze only. No CSV parsing, Silver normalization,
reference publication, canonical identity, packet mapping, strategy, IV/Greeks,
eligibility or decision-loop changes. FS2b3 must add a versioned native HTTP decoding
and reference-normalization adapter. Never relabel native captures as offline imports.

## Evidence and dependency decision

Sources reviewed in the prior implementation turn:
- https://kite.trade/docs/connect/v3/market-quotes/
- https://kite.trade/docs/connect/v3/changelog/
- https://docs.python.org/3/library/http.client.html

Use public stdlib http.client, not SDK-private parsers or parsed instrument lists.
Kite v3 request uses X-Kite-Version: 3 and Authorization: token api_key:access_token.
One GET to verified HTTPS api.kite.trade, /instruments or /instruments/<EXCHANGE>.
Uppercase exchange grammar restricts the route, not provider exchange support.
No redirects, retries, conditional requests, token refresh or proxy/certificate bypass.

## Exactness, limits and clocks

Capture version kite-instrument-http@1; command ingest.kite_instruments_http@1;
source kite_instruments_http. Body bytes are application entity-body bytes after
HTTP transfer framing/TLS removal; content coding such as gzip is preserved unchanged.
This is not raw TLS/HTTP wire capture. Only allowlisted parsed headers are recorded,
with lowercase names and selected values/duplicates in order. Not original header
bytes, status-line bytes, arbitrary headers or trailers. Cookie/Set-Cookie, Location
and Authorization are excluded. Provider Date/Last-Modified/ETag are assertions only.

Default body cap 8 MiB plus one retained sentinel byte; chunk size <=64 KiB. Oversized
advertised bodies can be rejected before body reads. Exception partial bytes are
retained within that same bound; any returned bytes not retained are explicitly counted.
Hashes refer only to captured bytes. Selected headers: <=32 entries, value length
<=2048 characters, JSON-encoded selection <=16 KiB. Full metadata <=32 KiB. Ambiguous
or unsupported HTTP framing fails closed; no partial-body salvage for reference data.

Connect timeout 5s, socket inactivity timeout 10s, elapsed budget 60s checked BETWEEN
reads. This is not a hard total wall-clock deadline; blocking reads or slow trickles
can exceed elapsed budget before returning. No stronger performance guarantee.

Separate aware UTC request-start, headers-returned, first-chunk-returned and capture-end
clocks. They are application observations, not exact kernel byte arrival. Bronze
received_at means LOCAL_CAPTURE_END_NOT_EXCHANGE_OR_PUBLICATION; metadata preserves
other clocks. Bronze recorded_at is later insertion time. Exchange time, instrument
validity dates and provider/platform publication remain unknown/null. HTTP Date is
not publication. No available_at shortcut or fabricated historical availability.

## Persistence, audit and attempt identity

One caller-selected capture_session_id identifies one attempted connection, including
failures. Existing A1 job or stored source/session blocks refetch under that identity.
A separately reviewed new attempt requires a new session. Never repair the old audit
state or manufacture success. Execution is planned/running in A1 before fetch.

One atomic FS1a batch stores response-body and canonical response-metadata. Metadata
links body capture_event_id, envelope_hash and payload_hash, completeness, clocks,
policy, selected headers and bounded reason codes. Exact captured body is also the
input artifact. Origin live_provider; exchange_ts null. A zero-byte body placeholder
with body_observed=false means no body was observed, not that an unreceived provider
response was empty. Complete empty responses are distinguished by status/completeness.

Rejected/non-200/partial/empty evidence is preserved, then the A1 job fails. CAPTURED
means complete nonempty HTTP 200 only; arbitrary malformed CSV or HTML remains
unvalidated Bronze (UNVALIDATED_HTTP_CAPTURE), never published market reference data.
No raw body, credential, arbitrary exception text or account notification is logged.
Credentials are included only in the in-memory request, not application plans/metadata.

Body and metadata insert transaction is separate from A1 completion. A crash may leave
committed evidence and incomplete audit. Unexpected adapter failures can leave audit
without body. Explicit initialization retains existing A1/FS1a bootstrap behavior;
plan never initializes DB/schema. One owner for the dedicated Bronze DuckDB.

In-progress response is bounded RAM, not an fsync-backed HTTP journal. Process crash
before Bronze commit can lose bytes. No crash-recovery/losslessness certification.
The separate FS1b WebSocket journal/backpressure implementation is unchanged.

## Subsequent normalization and replay

FS2b3 must pin and verify both body and metadata variants, audit state and conflicts
BEFORE quality filtering. Reject incomplete bodies; version bounded decompression,
encoding/trailing-data policies and CSV normalization. Preserve actual receipt/recording
semantics without synthesizing publication. Never use offline re-import as a provenance
shortcut. Later publication/bundle/validity ledgers must support exact_decision_replay,
as_known_at and explicitly labelled research_recomputed. This package enables none
of those joins by itself. Invalidation selection must precede quality filtering.

See VALIDATION.txt for executed offline tests versus supplied project integration tests.
No broker requests or live-market tests were executed during generation.
