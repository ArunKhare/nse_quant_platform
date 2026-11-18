# Option Stream Medallion Migration

## Purpose

Migrate existing legacy `option_stream` rows into Medallion Bronze as immutable historical-import artifacts.

## Safety

- Historical import only.
- No live acquisition.
- No trading.
- No production cutover.
- No deletion or mutation of `option_stream`.
- No decision eligibility.
- Idempotent by canonical snapshot identity.

## Commands

Dry run:

```powershell
uv run python scripts/migration/migrate_option_stream_to_medallion.py `
  --underlying NIFTY `
  --start-date 2026-11-01 `
  --end-date 2026-11-18 `
  --code-revision <git-sha> `
  --mode dry-run
```

Apply:

```powershell
uv run python scripts/migration/migrate_option_stream_to_medallion.py `
  --underlying NIFTY `
  --start-date 2026-11-01 `
  --end-date 2026-11-18 `
  --code-revision <git-sha> `
  --mode apply
```

## Flow

```text
option_stream
  -> grouped immutable snapshot
  -> canonical JSON
  -> snapshot_id
  -> Bronze historical_import artifact
  -> migration ledger
```

## Ledger

`medallion_migration.option_stream_migration` records snapshot identity, Bronze pins, status, and errors.

## Next

After Bronze migration, derive Silver option-chain observations from Bronze; do not derive Silver directly from `option_stream`.
