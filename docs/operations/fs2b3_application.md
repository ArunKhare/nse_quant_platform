# FS2b3 application and QA

ZIP root folders match the project: src/, scripts/, tests/, docs/. No source/ wrapper.
This is an additive implementation candidate. Extract outside the repository. Choose
ONE method: guarded patch application OR copying the ten project files to matching
folders. Never apply the patch after copying; never overwrite a conflicting new file.
Existing acquisition, framing/B008 corrections, FS2a/FS2b1, health/drain remain untouched.

Example extraction directory C:\Temp\FS2b3. From project root:

```powershell
Set-Location C:\Projects\nse_quant_platform
uv run python C:\Temp\FS2b3\apply_fs2b3.py --repository .
git branch --show-current
uv run python --version
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

The Python helper avoids unsigned PowerShell scripts. It requires a clean
feat/medallion-feature-store branch and successful git apply --check. It does not
commit, create production schemas or contact the broker. Preserve Python >=3.12 and
validate the actual uv runtime, including 3.14.2 if used. Supplied real integration tests
use injected captures and require no credentials or live requests.

## Plan existing native receipts, offline only

Obtain exact body/metadata variant IDs from the separately reviewed FS2b2 acquisition
receipt or existing read-only inspection. Never automatically choose a conflicting
variant or use the most recent instrument snapshot as a historical fact.

```powershell
uv run python scripts/ingest/normalize_native_instrument_reference.py `
  --bronze-db C:\Data\nse\bronze.duckdb `
  --silver-db C:\Data\nse\silver.duckdb `
  --body-capture-event-id <EXACT_SHA256> `
  --body-envelope-hash <EXACT_SHA256> `
  --metadata-capture-event-id <EXACT_SHA256> `
  --metadata-envelope-hash <EXACT_SHA256>
```

Plan is unverified and opens neither DB, even with --initialize. For separately reviewed
offline execution, add --execute --actor <ACTOR> --code-revision <REVIEWED_REVISION>.
Use --initialize only to explicitly initialize the new Silver dataset/A1 schema. Ensure
parent directory exists and a single process owns the writer; Bronze is read-only.
No --allow-network flag or credentials are needed because there is no network path.

COMMITTED may mean an immutable quarantine assessment. Check classification/reason and
audit state, not just exit status. Normalized results are not published or eligible.
The actual source receipt gate state can evolve after normalization; resolve current
supersession/invalidation BEFORE any future quality-filtered consumer. Never reactivate
an older good row after later quarantine. No read API or decision cutover is provided.

Suggested commit after local integration and full QA:

feat(data-platform): normalize native HTTP instrument references into Silver

- verify pinned body/metadata, exact artifacts, batch and acquisition audit evidence
- decode bounded single-member gzip with explicit no-salvage policies
- preserve nullable provider fields and exact decimal observations
- append versioned Silver assessments with explicit gate-state supersession
- retain actual source clocks without inventing validity/publication times
- add pure, isolated storage and supplied native-pipeline integration tests
