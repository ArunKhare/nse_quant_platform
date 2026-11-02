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
    if ($branch.Trim() -ne 'feat/medallion-feature-store') {
        throw "Unexpected branch: $branch"
    }
    Invoke-Checked git @('rev-parse', 'HEAD')
    Invoke-Checked git @('status', '--short')
    Invoke-Checked uv @('run', 'python', '-c', 'import sys; print(sys.version); assert sys.version_info >= (3,12)')
    $paths = @(
        'pyproject.toml',
        'src/nse_quant/strategy/exit_engine.py',
        'tests/strategy/test_decision_loop_position_monitoring.py'
    )
    foreach ($path in $paths) { Get-FileHash -Algorithm SHA256 -LiteralPath $path }
    Invoke-Checked uv @('run', 'pytest', '-p', 'scripts.qa.iv_collapse_probe',
        'tests/strategy/test_decision_loop_position_monitoring.py::test_position_closes_on_iv_collapse',
        '-vv', '-rA')
    Invoke-Checked uv @('run', 'pytest', 'tests/data_platform', '-q')
    Invoke-Checked uv @('run', 'pytest', 'tests', '-q')
    Invoke-Checked uv @('run', 'ruff', 'check', 'src/nse_quant/data_platform',
        'scripts/inspect', 'scripts/ingest', 'tests/data_platform')
    Invoke-Checked uv @('run', 'ruff', 'check', 'scripts/qa/iv_collapse_probe.py',
        'tests/strategy/test_iv_collapse_probe.py')
    Invoke-Checked uv @('run', 'mypy')
    Invoke-Checked git @('diff', '--check')
} finally { Pop-Location }
