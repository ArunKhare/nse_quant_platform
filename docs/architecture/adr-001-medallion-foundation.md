# ADR-001: Medallion layers with availability-aware feature publication

Status: proposed for local adoption; implementation limited to foundation primitives.

## Context

Existing tables mix observed/derived values and several maintenance paths replace
historical data. Exact decision reproduction needs both preserved inputs and preserved
feature revisions. CLI consolidation alone cannot establish those guarantees.

## Decisions

1. Bronze append-only source preservation; Silver source-aware normalized revisions;
   Gold versioned derived builds.
2. Original capture, historical reconstruction and operational publication are distinct.
3. Preserve event, receipt/durability and publication times; freeze decision knowledge.
4. Pin versions, input snapshots and quality contracts; save consumed bundles.
5. One operational write owner initially; independent research reads published archives.
6. Audit contracts, jobs and lifecycle events through a shared package; audit all exports
   as well as database writes. Use domain outbox/reconciliation for cross-resource safety.
7. No immediate wholesale dependency on an external feature-store framework.
8. No blind table rename or metadata backdating during legacy migration.

## Alternatives rejected for now

- Rename option_stream Bronze: historical analytics can already have changed.
- Add --overwrite everywhere: does not preserve lineage or establish source ownership.
- Multiple DuckDB-writing processes: no unplanned shared-file writer topology.
- Event-time-only joins: allow later backfills to leak into earlier decisions.
- Folder-only medallion: does not enforce dataset identity or write boundaries.

## Consequences

More revisions/manifests and explicit storage/retention costs. Additional services may
become necessary as concurrent load grows. Backfills become build/import operations.
Retrospective research remains possible but must not masquerade as decision-time truth.
The initial application audit API is not tamper-proof or full production enforcement.
