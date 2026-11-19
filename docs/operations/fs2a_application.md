# Apply and QA

Reconstructed additive delivery; review patch first. Nothing has been applied to the
user repository. Expected branch: feat/medallion-feature-store.

```powershell
.\Apply-FS2a.ps1 -Repository C:\Projects\nse_quant_platform
Set-Location C:\Projects\nse_quant_platform
git branch --show-current
uv run python --version
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

Preserve pyproject.toml >=3.12. Verify your local 3.14.2 compatibility; optionally also
run `uv run --python 3.12 pytest tests/data_platform -q` if that interpreter is available.
Do not weaken tests, schema policy or dependencies to make this candidate pass.

Plan only, replace SHA placeholders with exact pinned variant hashes:

```powershell
uv run python scripts/ingest/normalize_kite_bronze.py `
  --bronze-db C:\Data\nse\bronze.duckdb `
  --silver-db C:\Data\nse\silver.duckdb `
  --capture-event-id <EXACT_SHA256> `
  --envelope-hash <EXACT_SHA256>
```

Default plan opens no DB and labels inputs unverified. For separately reviewed offline
execution, close other database owners; ensure parent directory exists; add --execute,
--actor <ACTOR>, --code-revision <REVIEWED_REVISION>, and --initialize only when explicitly
initializing the dedicated Silver schema. Never choose conflict winners automatically.
No broker operations occur. COMMITTED does not mean published, eligible or decision-ready.

Proposed commit message after actual local QA:

feat(data-platform): add versioned native Kite Silver frame decoding

- independent bounded parser with strict no-salvage framing
- immutable Silver frame dispositions with exact Bronze lineage
- audited offline service and side-effect-free default plan
- protocol fixtures and supplied A1/FS1a integration tests
- document protocol, availability limitations and FS2b boundary
