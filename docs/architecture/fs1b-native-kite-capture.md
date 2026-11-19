# FS1b: native raw Kite capture and sealed-segment Bronze ingestion

Status: new target-path implementation; not live-tested or production-certified.
Requires QA-passed A1/A2 and corrected FS1a Bronze storage/import. No legacy wrappers,
option_stream writes, tick normalization, IV/Greeks enrichment or strategy execution.

## Source boundary

Capture at KiteTicker.on_message(client, payload, is_binary), before normalizer or
feature calculation. The official Python SDK calls on_message before its binary
parse/on_ticks path. This is the SDK-exposed WebSocket message payload, not TLS bytes,
HTTP handshake bytes or a claim that every wire/control frame is exposed.

Binary bytes are preserved exactly. Text already supplied as str is explicitly
labelled kite_ws_text_reencoded_utf8; do not call reconstructed UTF-8 original wire
bytes. Byte text payloads retain their bytes with a different representation label.
No exchange timestamp is invented from local receipt time. Exchange timestamps and
instrument mappings will be decoded in Silver. Raw heartbeats/text are not filtered.
Text may include account/order notifications: protect access/retention; do not publish
raw account messages as public research data.

Reference: https://github.com/zerodha/pykiteconnect/blob/master/kiteconnect/ticker.py
Pin and verify the installed SDK in deployment; behavior must be integration-tested.

## Files

native_kite_capture.py: durable segmented journal, callbacks, validation.
kite_capture_cli.py: bounded native SDK session with A1 audit.
drain_capture.py: verified immutable-buffer input -> audited FS1a store.
scripts/ingest/capture_kite_raw.py and drain_kite_capture.py: thin CLIs.
Tests: no-network journal/controller suite plus local real audit/Bronze integration.

## Durability and backpressure

The callback receives time at entry, allocates a receipt sequence under the journal
lock, serializes the envelope, writes all bytes, flushes and fsyncs before success.
There is no accepted-event RAM queue. Synchronous I/O is explicit backpressure, not
an assertion that provider buffers cannot overflow or disconnect under load.

Do not run another collector to write the same journal. Session directory and segment
files are created exclusively. Closed segments are not edited. Original raw records
are never rewritten by draining. Record IDs identify receipt frames, not economic ticks.

Defaults: 1 MiB raw payload, 8 MiB segment, 1000 records per segment, 1 GiB session
budget and 120-second capture. Exhaustion/oversize/fsync/write/connection failures are
fatal to the clean-session contract, not silent dropping. Failure may leave a partial
last record; preserve it for recovery review. No automatic truncation/deletion occurs.

fsync completion is the local durability boundary used here. This does not guarantee
power-loss survival on every filesystem/device; directory metadata persistence,
Windows storage behavior, disk-full, hardware cache and kill/restart require testing.

## Session and reconnect policy

Auto-reconnect is intentionally disabled. Unexpected disconnect fails the session.
A later connection uses a new UUID capture_session_id; do not splice a missing period
into one seemingly continuous successful session. Subscription list and capture limits
are part of the audited plan. Subscription/instrument discovery is explicit via tokens;
there is no automatic claim of multi-expiry or research-grade coverage.

After the requested duration, stop intent is set, WebSocket close is requested through
the reactor thread, and close confirmation is awaited. Frames delivered during graceful
shutdown are still persisted until the SDK close callback. Only then seal the journal.
KeyboardInterrupt, failed startup, unexpected close, persistence error or close timeout
must not be reported as clean. Incomplete/FAILED sessions are not auto-drained.

Each successful close creates per-segment seals and session_final.json. Failed startup
or catastrophic storage failure may leave no final file at all. That is incomplete,
not evidence of completion. Empty clean capture means no data, not feature availability.

## Audit ownership

The main CLI thread owns a per-session audit.duckdb. The SDK callback writes only the
raw journal and never touches DuckDB. The capture job encompasses authentication,
connection, capture and shutdown. Do not store credentials or raw payloads in audit
metadata. Existing authentication helper is used only after --execute.

Journal creation precedes audit initialization; a startup failure may leave an empty
incomplete session directory. That directory is not successful market capture.
Cross-resource audit/seal finalization is not atomic. Draining requires both CLOSED
metadata and a SUCCEEDED capture.kite_raw@1 audit job. Interrupted finalization needs
manual review/reconciliation, not automatic state rewriting.

## Draining

Default drain validates seals and the completed audit without writing domain data.
Validate all declared segments: order, session identity, record sequence, row counts,
size, checksum, and absence of unsealed extras. Reject path traversal/symlinked objects.
The execute path rereads each bounded segment into immutable bytes and verifies against
its pinned seal hash immediately before parsing and append. This prevents accidentally
accepting a changed file after initial planning.

Store the exact JSONL segment as the input artifact and exact frame bytes as payloads.
Parent/child jobs identify the capture session and segment hashes. Deterministic batch
keys make committed segment retries idempotent. No mutable checkpoint file is required:
Bronze ingest_batches is the durable receipt. A partially completed drain can rerun
all segments with the same immutable identities; previously committed batches retry.

Every segment is atomic, not the whole session. A later segment failure does not roll
back earlier committed segments. No exactly-once network-delivery claim is made.
COMMITTED_WITH_CONFLICTS means preserved evidence requiring review; it is not Silver
eligibility. EMPTY_SESSION is not data. Output DB/manifests must be outside source session.

## Plan-only examples

Supply your reviewed actual instrument tokens; 123 below is only a placeholder and
must not be mistaken for an NIFTY contract selection.

    uv run python scripts/ingest/capture_kite_raw.py --tokens 123 --journal-root data/bronze/journals --seconds 120

Default capture mode performs no authentication, subscription, network or directory
creation. Execution needs --execute --code-revision YOUR_COMMIT, a valid authenticated
Kite setup, reviewed subscriptions and completed local validation. No live command was
executed while building this package.

After a real, clean, audited session closes:

    uv run python scripts/ingest/drain_kite_capture.py --session-dir data/bronze/journals/SESSION_ID --bronze-db data/bronze/capture.duckdb --manifest-root data/bronze/ingest_manifests

Default drain is read-only verification. Actual ingestion additionally needs --execute
--code-revision YOUR_COMMIT; use --initialize only for an explicitly dedicated new DB.
Never target the legacy operational DB. Do not drain active/failed/unsealed sessions.

## Legacy retirement

This command does not call or adapt the old enriched kite_stream collector. Do not
run both as an accidental dual-capture path. Stop using the old collector for new
Bronze capture; retire its operational launch references after validating this native
collector. Preserve its historical data through the explicit legacy migration service,
not by labelling enriched snapshots raw. No automatic deletion is performed here.

The decision loop is not wired to consume these raw frames. Silver decoding, stable
instrument metadata, spot/option synchronization and feature construction must land
before native decision consumers are switched. Do not bypass those stages to restore
the old mixed capture/analytics architecture.

## Validation and remaining acceptance

20 no-network tests executed: raw byte fidelity, rotation/order, checksums, incomplete
sessions, fsync failures, byte budget, session reuse, late shutdown frames, representation
labels, subscription, connect timeout, persistence failure, plan-only behavior and tokens.
An integration test using actual installed A1/FS1a classes is included for local QA.

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Not performed here: real SDK/Twisted lifecycle, authentication, broker subscriptions,
Windows file sync/locking, operational load, process kill, recovery, backup restoration
or full integration. Measure callback fsync latency/backlog and disconnect/gap rates
before sustained capture. A bounded durable async spool may follow measured need, but
must retain the same acknowledgement/failure contract, never a drop-on-full queue.

Next native package: recovery/health inspection and Silver raw-frame decoding with
versioned instruments and availability-aware observation selection.
