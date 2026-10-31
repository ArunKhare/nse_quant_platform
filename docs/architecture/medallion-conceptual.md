# NSE Quant medallion architecture and point-in-time feature store

Status: target architecture; foundation implementation only. Not a production certification.
Decision date: 2026-10-31. Architecture version: 1.

## 1. Purpose and boundaries

Preserve first-hand observations, distinguish repairs from originals, build reproducible
analytics, and reproduce exactly which inputs each decision consumed. The present
option_stream mixes capture and calculated analytics. It is a legacy mixed dataset,
not proof of immutable raw capture. No existing data is automatically reclassified as raw.

```text
Provider events / acquired files / historical downloads
                  |
                  v
BRONZE: original payloads + receipt/source/session metadata
                  |
       normalization and quality validation
                  v
SILVER: typed observations + revisions + source lineage
                  |
        versioned calculations on pinned inputs
                  v
GOLD: curated analytical feature builds
                  |
      point-in-time retrieval + bundle publication
                  v
Decision evidence: exact bundle and revision IDs
```

Audit, contracts, manifests, schemas, ownership, retention and recovery cross every layer.
Medallion is a responsibility and quality model, not merely three folder names.

## 2. Bronze

Datasets: option_events, spot_events, broker_candle_batches, bhavcopy_files,
instrument_files. Preserve original provider bytes/files where transport permits,
otherwise document the earliest retained decoded representation. Do not label a
re-serialized quote as the original wire message.

Store capture_event_id, provider, capture_session_id, provider event identity/sequence
if supplied, exchange_ts if supplied, received_at, durable_at, payload_hash, schema
version and original instrument identifiers. Missing exchange time stays missing.
Retried ingestion and conflicting duplicates have different outcomes: exact retries
are identifiable; conflicts are preserved/quarantined, not silently replaced.

No analytical job may update/delete Bronze. Corrected provider observations append
and reference the prior observation when identifiable. Retention is an explicit,
audited administrative process, not a backfill side effect.

## 3. Silver

Datasets: option_quotes, spot_quotes, acquired_candles, instrument_versions,
observation_quality. Parse types, validate prices, normalize timestamps, retain raw
lineage, resolve stable contract identity, and represent corrections explicitly.

Store source_observation_id, revision_id, recorded_at, schema version, validation
status/reasons and a lineage reference. Stable identity includes venue and instrument
validity; a provider token alone is not a perpetual contract identity.

Quality checks include crossed/stale quotes, absent timestamps, invalid instrument
metadata, source gaps, incomplete snapshots and incompatible spot/option timestamps.
Quarantined input remains discoverable. Silver selection policy defines which
revision is canonical for which knowledge boundary.

## 4. Gold

Datasets: contract_analytics, aggregated_candles, atm_iv, term_structure,
spot_features, daily_rv, regime_features and research_panels.

Every build pins input snapshot, feature definition, code/configuration, units, source
selection, calculation/expiry/rate policy, quality requirements, warm-up window and
availability rules. Retain earlier published builds. A Gold label does not imply
that a feature is fresh, complete or eligible for a strategy.

Publish IV and Greeks coherently. Keep expiry and tenor-pair dimensions. Distinguish
partial-session features from completed-session features. Do not overwrite valid
features with incomplete warm-up results. Original broker candles and derived
aggregates must have separate identity/storage ownership.

## 5. Time and point-in-time retrieval

Use timezone-aware UTC instants for storage, and the explicit exchange trading
calendar/timezone to derive session dates. Do not use host-local timezone conversion.

- event_ts: source event time or explicitly defined window end.
- received_at/durable_at: when the platform received/preserved source data.
- published_at: when a validated feature revision was actually visible.
- publication_seq: committed publication order under one publication owner.
- market_as_of: decision's permitted market event boundary.
- knowledge_cutoff: frozen publication/knowledge boundary for that decision.

Eligibility requires entity/version match, event/input cutoffs <= market_as_of,
publication visibility <= knowledge boundary, TTL compliance, quality compliance,
and coherent input policies. Do not backdate publication during historical builds.
Resolve invalidation revisions before filtering quality; do not resurrect superseded
values accidentally. Explicitly specify whether fallback to an older observation is allowed.

Retrieval modes:
1. exact_decision_replay: follow saved bundle/revision IDs.
2. as_known_at: reconstruct eligible revisions at a historical publication boundary.
3. research_recomputed: calculate a selected version from historical input, labelled
   retrospective; never claim it was operationally published at the earlier time.

A 10:00-10:15 bar published at 10:15:02 is unavailable to a 10:15:01 decision.
Daily metrics must not become visible at midnight before their session finishes.
Late input is ineligible before its platform availability even with an earlier event time.

## 6. Decision bundles

A published bundle contains bundle_id, symbol, market_as_of, knowledge_cutoff,
publication boundary, feature-set version, selected revision IDs, input lineage,
quality and unavailable reasons. Feature values must be consistent with one frozen
selection boundary. Missing deferred expiry remains unavailable, not synthesized.
Persist exact consumed bundles even if calculation or retrieval policies later change.

## 7. Process and storage ownership

Initial design: one owning operational writer; durable append-only capture;
manifested immutable archives for independent DuckDB research; consumer access via
published artifacts or a service boundary. Do not launch independent writers against
the live DuckDB file. Separate audit DBs also require an ownership policy.

DuckDB remains useful for the foundation and offline analysis. A server database
may later own concurrent operational metadata/serving if measured requirements justify
it. No automatic commitment to Feast, Redis, Kafka, Delta or a cloud vendor.
Atomicity across domain publication and a separate audit DB is not assumed: use
transactional intent/outbox and reconciliation in the later publication implementation.

## 8. Audit and security

All writing/export commands must have command identity, operation category, actor,
parent job, code/config identifiers, sanitized scope, input snapshots, output builds,
counts, validation and publication status. Never log secrets or unrestricted argv.

Append-only application APIs are not tamper-proof storage. Enforce ownership,
permissions, controlled administrative access and off-host/tamper-evident audit
retention before production sign-off. Hashes alone do not prevent privileged edits.

## 9. Script hierarchy

scripts/ingest: source -> Bronze.
scripts/normalize: Bronze -> Silver.
scripts/build: Silver -> Gold.
scripts/publish: validated versions -> selected outputs.
scripts/export: pinned dataset -> artifact; no repair side effects.
scripts/inspect: read-only domain operations.
scripts/workflows: parent audit + registered children; no duplicate domain SQL.

Thin CLIs delegate to package services. Move names only after callers, tests and
external launchers migrate. Retirement is a separate audited change.

## 10. Quality, failure and production acceptance

Require deterministic retry/conflict behavior, validation before visibility, rollback
for failed replacements, manifest/checksum verification, backup restore exercises,
restart reconciliation, monitoring, capacity tests and disk-full/partial-write tests.
Set measured freshness/latency, RPO/RTO, retention, and capacity targets before rollout.
These targets remain open; none is invented by the initial patch.

## Sources and baseline

Repository evidence: persistence/duckdb_store.py, backfill_option_iv.py,
backfill_option_greeks.py, backfill_iv.py, bootstrap_nse_eod_iv.py,
build_daily_rv.py, features/spot_features.py, research/iv_surface.py,
research/iv_regimes.py, market_data/replay_exporter.py and eod_maintenance.py.
The inspected snapshots may predate local cleanup commits. Reconcile local HEAD first.

Public background:
- https://docs.databricks.com/aws/en/lakehouse/medallion
- https://docs.feast.dev/getting-started/concepts/point-in-time-joins
- https://duckdb.org/docs/lts/connect/concurrency
