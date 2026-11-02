param([string]$Repository = 'C:\Projects\nse_quant_platform')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)" }
}
Push-Location $Repository
try {
    $branch = & git branch --show-current
    if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve Git branch' }
    if ($branch.Trim() -ne 'feat/medallion-feature-store') { throw "Unexpected branch: $branch" }
    Invoke-Checked git @('rev-parse', 'HEAD')
    Invoke-Checked git @('merge-base', '--is-ancestor', 'e262db2', 'HEAD')
    Invoke-Checked git @('status', '--short')
    Invoke-Checked uv @('run', 'python', '-c', 'import sys; print(sys.version); assert sys.version_info >= (3,12); from nse_quant.data_platform import checkpoint_native_revalidation as n; assert n.VERSION == "checkpoint-pinned-native-policy-revalidation@1"')
    Invoke-Checked uv @('run', 'pytest', 'tests/data_platform/test_delegation_review.py',
        'tests/data_platform/test_delegation_native_reader.py', '-q')
    Invoke-Checked uv @('run', 'pytest', 'tests/data_platform', '-q')
    Invoke-Checked uv @('run', 'pytest', 'tests', '-q')
    Invoke-Checked uv @('run', 'ruff', 'check', 'src/nse_quant/data_platform',
        'scripts/inspect', 'scripts/ingest', 'tests/data_platform')
    Invoke-Checked uv @('run', 'mypy')
    Invoke-Checked git @('diff', '--check')
} finally { Pop-Location }
