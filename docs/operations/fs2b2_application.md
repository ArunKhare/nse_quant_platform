# Application and QA

ZIP root folders match the project: src/, scripts/, tests/, docs/. No source/ wrapper.
Choose ONE installation method:
1. Extract outside the repository; review fs2b2.patch; run the guarded script on a clean
   expected branch. No DB, credentials, broker request or commit occurs on application.
2. Manually copy only the eight project files to matching folders. Then DO NOT run the
   application script or apply the patch again. Refuse conflicts rather than overwrite.

```powershell
.\Apply-FS2b2.ps1 -Repository C:\Projects\nse_quant_platform
Set-Location C:\Projects\nse_quant_platform
git branch --show-current
uv run python --version
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

Expected branch feat/medallion-feature-store. Preserve pyproject.toml >=3.12; validate
the actual uv runtime including 3.14.2 if selected. All supplied tests inject HTTP;
no broker request or credentials are needed. Run full QA locally before committing.

## Safe plan

```powershell
uv run python scripts/ingest/capture_kite_instruments_http.py `
  --bronze-db C:\Data\nse\bronze.duckdb `
  --capture-session-id reviewed-http-reference-001 `
  --exchange NSE
```

No network, credential lookup, DB creation or schema initialization. Omit --exchange
for /instruments. Session availability is explicitly unverified in plan mode.
--allow-network without --execute remains plan-only.

## Separate reviewed network execution, NOT part of QA

Approve exact account, endpoint, actor/revision, session, target and policy first.
Only then add BOTH --execute and --allow-network, plus --actor and --code-revision.
Use --initialize only for explicitly approved A1/Bronze bootstrap; ensure parent path
exists and only one writer owns the dedicated Bronze DB.

Provision KITE_API_KEY and KITE_ACCESS_TOKEN securely in the process environment before
approved execution. No CLI credential values, login, token refresh or interactive auth.
Do not paste secrets into shared history, logs or issue reports. Package generation
does not constitute approval for a live operation.

Non-200 responses, including 304/401/403/429, fail without retry. Evidence may commit
while the job fails, so exit 1 does not necessarily mean zero writes. Review the returned
variant IDs and A1/Bronze read-only evidence; never manufacture old job success or reuse
its session to fetch again. A separately reviewed retry needs a new session identity.

CAPTURED does not mean CSV validated, normalized, published, eligible or production-ready.
Do not re-import native bytes through FS2b1 offline provenance. Native HTTP decoding and
reference normalization are explicitly FS2b3 work.

Proposed commit after local QA:

feat(data-platform): add audited native Kite instrument HTTP acquisition

- preserve content-coded body and linked metadata in atomic Bronze batches
- record receipt clocks, completeness and explicit rejection dispositions
- require fixed verified HTTPS endpoint and explicit network gates
- block redirects, retries and reuse of attempted session identities
- add offline protocol and supplied A1/FS1a integration tests
- document publication and pre-commit durability limitations
