# FS2c1 application and local QA

The ZIP root matches project src/scripts/tests/docs. No source/ wrapper.
Nine added project files, no existing source/schema replacements. Extract OUTSIDE the
repository, review the patch and choose exactly one installation method:
- Use the guarded Python helper on a clean expected branch; or
- Copy the nine project files manually, then DO NOT also apply the patch.

Example extraction C:\Temp\FS2c1. From project root:

```powershell
Set-Location C:\Projects\nse_quant_platform
uv run python C:\Temp\FS2c1\apply_fs2c1.py --repository .
git branch --show-current
uv run python --version
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

The helper requires feat/medallion-feature-store, clean worktree and git apply --check.
It does not switch/reset branches, commit, initialize DBs or execute broker operations.
Keep Python >=3.12 and test actual uv runtime, including 3.14.2 if selected. Supplied
pipeline integration tests use only injected HTTP captures and need no credentials.

## Read-only exact assessment inspection

Use a revision returned by a separately reviewed FS2b3 normalization. Do not choose
"latest normalized" in SQL: that can resurrect a superseded value after quarantine.

```powershell
uv run python scripts/inspect/inspect_native_reference_token.py `
  --bronze-db C:\Data\nse\bronze.duckdb `
  --silver-db C:\Data\nse\silver.duckdb `
  --assessment-revision-id <EXACT_SHA256> `
  --instrument-token <PROVIDER_TOKEN>
```

This defaults to inspection and has no --execute, --initialize, --allow-network,
--output-file or credential options. Both DBs open read-only. Missing DBs are not
created. No schema/domain-data writes, no broker access, no audit lifecycle mutations.

Check status and reason_code. Exit0 means inspection completed, not that a token matched,
was published, or is eligible. A superseded/ambiguous/failed-audit/unsupported assessment
must not fall back to a previous good row. Review referenced assessments separately.
A fresh Bronze conflict can block a previously normalized assessment even before a new
Silver quarantine exists. Do not manually repair the source or old audit state.

Unique row references prove only snapshot-specific provider-token evidence. Do not
join historical ticks or cut over decisions as if economic validity/publication were
established. Cross-database inspection is not a transactionally atomic publication.

Suggested commit after full local QA:

feat(data-platform): add invalidation-aware native reference lookup
