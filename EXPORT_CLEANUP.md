# Export cleanup: first migration only

This bundle is not an applied repository change. Extract the src/, scripts/, and tests/
folders into the repository root, reviewing overwritten legacy scripts first.

The daily-runner-migration.patch is a zero-context patch targeting the two old script
path literals. From the repository root, review and apply with:

    git apply --check --unidiff-zero daily-runner-migration.patch
    git apply --unidiff-zero daily-runner-migration.patch

If your daily runner already forwards --export-dir, retain only one copy per command.
If git cannot match your local version, manually replace the two old script literals
with scripts/export_warehouse.py and insert the respective subcommand immediately
after the script, followed by --export-dir and args.warehouse_dir.

Canonical commands (from repository root):

    uv run python scripts/export_warehouse.py option-stream --date 2026-10-30
    uv run python scripts/export_warehouse.py market-regimes --start-date 2026-10-20 --end-date 2026-10-30

Both accept --underlying or --symbol, default NIFTY, and --export-dir, default data/exports.
The old scripts remain compatible, including public path builders and patchable store
factories. No deprecation warning is emitted to avoid changing scheduled-job logs.

Preserved: projected option columns/order, partition paths, ZSTD, row ordering,
option empty-data exit 1, regime empty-range success, delegated regime export logic,
exception propagation, caller-owned store lifecycle in library functions. The new
CLI validates dates/range before opening DuckDB. Legacy parsers retain their old
argument shapes and date strings. No destructive deletes or trading changes.

Validate locally:

    uv run pytest tests/test_warehouse_export_cleanup.py -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/persistence/warehouse_exports.py scripts/export_warehouse.py scripts/backfill_option_stream_exports.py scripts/backfill_market_regime_exports.py tests/test_warehouse_export_cleanup.py
    uv run mypy

Tests use mocked stores: additionally perform a temporary-database integration export
in your local environment and compare Parquet schemas/content with the prior scripts.
Do not overwrite production exports just to smoke-test this change.

Reference audit before retiring wrappers:

    git grep -n -E 'backfill_(option_stream|market_regime)_exports' -- .

Review docs, CI, tests, launchers, scheduled tasks and commands outside Git as well.
No project-wide unused-script conclusion is claimed. Other builders and backfills are
out of scope. IV policy, gates, sizing, and risk controls remain untouched.

Build verification here: Python syntax parsed successfully. Repository dependencies,
pytest, Ruff, mypy and database integration were NOT executed in this environment.
