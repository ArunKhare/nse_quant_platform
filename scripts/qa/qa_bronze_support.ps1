param([string]$Repository = 'C:\Projects\nse_quant_platform')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Push-Location $Repository
try {
    $branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve branch' }
    if ($branch -ne 'feat/medallion-feature-store') { throw "Unexpected branch: $branch" }
    & git status --short
    & git log -3 --oneline
    & uv run python -c "import sys; print(sys.version); assert sys.version_info >= (3,12)"
    if ($LASTEXITCODE -ne 0) { throw 'Python requirement check failed' }
    & uv run pytest tests/data_platform -q
    if ($LASTEXITCODE -ne 0) { throw 'data_platform tests failed' }
    & uv run pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw 'full tests failed' }
    & uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    if ($LASTEXITCODE -ne 0) { throw 'Ruff failed' }
    & uv run mypy
    if ($LASTEXITCODE -ne 0) { throw 'mypy failed' }
    & git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'git diff --check failed' }
    Write-Host 'Package QA passed, not whole-platform acceptance.'
} finally { Pop-Location }
