# Option Stream Medallion Migration

## Purpose

Migrate existing legacy `option_stream` rows into a dedicated Medallion Bronze database as immutable `historical_import` artifacts.

## Safety

- Historical import only.
- No live acquisition.
- No trading.
- No production cutover.
- No deletion or mutation of `option_stream`.
- No decision eligibility.
- Idempotent by canonical snapshot identity.
- Legacy source DB is opened read-only.
- Bronze writes go only to a dedicated Bronze DB.

## Artifact format

Legacy `option_stream` snapshots are preserved as:

```text
legacy-option-stream-snapshot@1
```

They are **not** reshaped into `native-option-chain-snapshot@1`.

The native option-chain codec requires a strict snapshot schema that legacy `option_stream` rows do not reliably satisfy. Forcing legacy rows into that format would misrepresent their provenance and structure.

## Migration flow

```text
legacy option_stream timestamp
  -> legacy-option-stream-snapshot@1 canonical JSON
  -> BronzeEvent
  -> Bronze append_batch
  -> immutable historical_import artifact
  -> audit job
  -> migration ledger
```

## Source label

Each snapshot receives a distinct source label:

```text
legacy_option_stream_historical_import:<content-hash>
```

The content hash includes:

- Underlying.
- Trading date.
- Snapshot timestamp.
- Exact legacy rows.

This satisfies Bronze first-write original-obligation semantics: one immutable scope per snapshot.

## Gap policy

Do **not** fill, interpolate, or synthesize missing `option_stream` data before Bronze migration.

Migrate rows exactly as they exist. Gaps are historical availability evidence and must be preserved, not fabricated.

Any later gap filling must be a separately versioned derived dataset, clearly labeled as estimated or interpolated, and must never overwrite Bronze.

## Commands

Dry run:

```powershell
uv run python scripts/migration/migrate_option_stream_to_medallion.py `
  --source-db .\data\nse_quant.duckdb `
  --bronze-db .\data\medallion_bronze.duckdb `
  --underlying NIFTY `
  --start-date 2026-10-18 `
  --end-date 2026-11-18 `
  --code-revision <git-sha> `
  --mode dry-run
```

Apply:

```powershell
uv run python scripts/migration/migrate_option_stream_to_medallion.py `
  --source-db .\data\nse_quant.duckdb `
  --bronze-db .\data\medallion_bronze.duckdb `
  --underlying NIFTY `
  --start-date 2026-10-18 `
  --end-date 2026-11-18 `
  --code-revision <git-sha> `
  --mode apply
```

Replace `<git-sha>` with the output of:

```powershell
git rev-parse HEAD
```

## Database separation

The script requires two distinct database files:

```text
--source-db   legacy nse_quant.duckdb, read-only
--bronze-db   dedicated medallion_bronze.duckdb, write target
```

The script refuses to run if both paths resolve to the same file.

## Bronze initialization

Before migration, the script initializes:

```text
BronzeEventStore
AuditLedger
migration ledger
```

This creates:

```text
bronze schema and Bronze tables
medallion_audit schema and audit tables
medallion_audit.option_stream_migration ledger
```

## Migration ledger

The ledger is:

```text
medallion_audit.option_stream_migration
```

It records:

- Underlying.
- Trading date.
- Snapshot timestamp.
- Source label.
- Snapshot ID.
- Bronze capture event ID.
- Bronze envelope hash.
- Bronze recording fingerprint.
- Status.
- Error code.
- Migration time.

A previously succeeded snapshot is skipped on rerun. A failed snapshot can be retried.

## Failure semantics

Common rejection meanings:

| Error | Meaning |
|---|---|
| `Use a dedicated Bronze DB, not the legacy source database` | Bronze target contains disallowed schemas or the same DB was passed as source and Bronze. |
| `FIRST_WRITE_ORIGINAL_OBLIGATION` | The same source-label scope was already written; each snapshot needs a distinct source label. |
| `SNAPSHOT_FIELDS_REQUIRED` | Legacy rows were incorrectly being validated against the native option-chain snapshot codec. |
| `Catalog Error: jobs does not exist` | Audit ledger was not initialized before Bronze preserve. |
| `Catalog Error: bronze.schema_versions does not exist` | Bronze was not initialized before the migration ledger. |

## Tests

```powershell
uv run pytest tests/data_platform/test_option_stream_history_migration.py -q
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check .
uv run mypy .
git diff --check
```

## Next step

After Bronze migration succeeds, derive Silver option-chain observations from Bronze.

Do **not** derive Silver directly from `option_stream`; that would bypass Bronze provenance and weaken Medallion lineage.
