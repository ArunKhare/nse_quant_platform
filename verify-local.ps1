param([string]$Repository = 'C:\Projects\nse_quant_platform')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $Repository
$branch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne 'feat/medallion-feature-store') {
    throw "Unexpected branch: $branch"
}
& git log -1 --format='%H %s'
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect HEAD' }
if (-not (Test-Path 'src/nse_quant/data_platform/quote_bundle_publication.py')) {
    throw 'Required prior research-publication writer is missing; reconcile source first'
}
& uv run python --version
if ($LASTEXITCODE -ne 0) { throw 'Runtime inspection failed' }
& uv run pytest tests/data_platform/test_quote_publication_reader.py tests/data_platform/test_quote_publication_inspect_cli.py -q
if ($LASTEXITCODE -ne 0) { throw 'Publication consumer tests failed' }
& uv run pytest tests/data_platform -q
if ($LASTEXITCODE -ne 0) { throw 'Data platform tests failed' }
& uv run pytest tests -q
if ($LASTEXITCODE -ne 0) { throw 'Full tests failed' }
& uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
if ($LASTEXITCODE -ne 0) { throw 'Ruff failed' }
& uv run mypy
if ($LASTEXITCODE -ne 0) { throw 'Mypy failed' }
& git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Diff check failed' }
