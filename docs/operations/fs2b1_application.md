# FS2b1 reconstructed artifacts: inspect before use

IMPORTANT: these are reconstructed conversation artifacts, not your verified local HEAD.
If corresponding files already exist, compare rather than overwrite. Your user-reported
green local checkout remains authoritative over this reconstruction.

ZIP directories directly match project root: src/, scripts/, tests/, docs/. No source/
wrapper. Eight Python files and two documents are included. ARTIFACT_INDEX.md lists them.

For MISSING files only, choose either manual copying of matching project paths OR the
reviewed additive patch. Do not use both. The Python helper requires clean expected
branch and successful git apply --check; existing conflicting files cause refusal.
Example extraction outside repository: C:\Temp\FS2b1.

```powershell
Set-Location C:\Projects\nse_quant_platform
uv run python C:\Temp\FS2b1\apply_fs2b1.py --repository .
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

Preserve pyproject.toml >=3.12 and validate actual local uv runtime, including 3.14.2.
Do not weaken current tests or use type-ignore comments to make reconstruction match.
See VALIDATION.txt: only the fresh pure/default-plan tests executed here; real A1/FS1a
integration and full QA are not certified by archive creation.

Plan-only file import (already acquired CSV; this never downloads anything):

```powershell
uv run python scripts/ingest/manage_instrument_reference.py import-file `
  --input C:\Data\nse\reviewed-instruments.csv `
  --bronze-db C:\Data\nse\bronze.duckdb `
  --import-session-id offline-review-001 --source-record-id artifact-001
```

Pinned normalization plan:

```powershell
uv run python scripts/ingest/manage_instrument_reference.py normalize `
  --bronze-db C:\Data\nse\bronze.duckdb --silver-db C:\Data\nse\silver.duckdb `
  --capture-event-id <EXACT_SHA256> --envelope-hash <EXACT_SHA256>
```

Plan opens no database. Separately reviewed offline execution needs --execute, --actor,
--code-revision and explicit --initialize only for intended schema bootstrap. Prepare
parent directory; retain single-owner DuckDB. No broker operations required. COMMITTED
can mean quarantine/conflicts, not published or decision-ready data.

Read-only evidence inspection:

```powershell
uv run python scripts/inspect/inspect_instrument_reference.py `
  --bronze-db C:\Data\nse\bronze.duckdb --silver-db C:\Data\nse\silver.duckdb `
  --reference-revision-id <EXACT_SHA256> --instrument-token <PROVIDER_TOKEN>
```

Do not relabel native HTTP captures as offline files to bypass FS2b2/FS2b3 evidence gates.
No automatic historical snapshot selection or contract resolution is provided.
