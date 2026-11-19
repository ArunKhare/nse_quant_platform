# Option Stream Silver Builder

Builds Silver option-stream observations strictly from dedicated Medallion Bronze.

## Commands

Dry run:

```powershell
uv run python scripts/migration/build_option_stream_silver.py `
  --bronze-db .\data\medallion_bronze.duckdb `
  --silver-db .\data\medallion_silver.duckdb `
  --underlying NIFTY `
  --start-date 2026-10-18 `
  --end-date 2026-11-18 `
  --code-revision <git-sha> `
  --mode dry-run
```

Apply:

```powershell
uv run python scripts/migration/build_option_stream_silver.py `
  --bronze-db .\data\medallion_bronze.duckdb `
  --silver-db .\data\medallion_silver.duckdb `
  --underlying NIFTY `
  --start-date 2026-10-18 `
  --end-date 2026-11-18 `
  --code-revision <git-sha> `
  --mode apply
```

## Safety

- Reads Bronze read-only.
- Writes only to dedicated Silver DB.
- Preserves Bronze lineage pins.
- Preserves missing values.
- Quarantines invalid rows; does not repair them.
- No trading, live acquisition, decision eligibility, or production cutover.
