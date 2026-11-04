param(
    [Parameter(Mandatory=$true)][string]$ExpectedHead,
    [string]$ReportPath = ''
)
$ErrorActionPreference = 'Stop'
if ($ExpectedHead -cnotmatch '^[0-9a-f]{40}$') { throw 'Full reviewed local HEAD required' }
$head = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $head -cne $ExpectedHead) { throw 'HEAD mismatch' }
$branch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -cne 'feat/medallion-feature-store') {
    throw 'Unexpected branch; review before executing'
}
& git status --short
if ($LASTEXITCODE -ne 0) { throw 'Worktree inspection failed' }
& uv run python -c "import sys; print(sys.executable); print(sys.version)"
if ($LASTEXITCODE -ne 0) { throw 'Interpreter inspection failed' }
Get-FileHash .\tests\data_platform\native_acceptance_case.py -Algorithm SHA256
if (-not $ReportPath) {
    $ReportPath = Join-Path (Get-Location) (
        'native-failure-acceptance-' + [Guid]::NewGuid().ToString('N') + '.json'
    )
}
if (Test-Path -LiteralPath $ReportPath) { throw 'Report exists; select a new path' }
$reportParent = Split-Path -Parent ([IO.Path]::GetFullPath($ReportPath))
if (-not (Test-Path -LiteralPath $reportParent -PathType Container)) {
    throw 'Report parent must already exist'
}
$oldPath = $env:PYTHONPATH
$oldReport = $env:NSE_NATIVE_FAILURE_REPORT
try {
    $testPath = Join-Path (Get-Location) 'tests/data_platform'
    $env:PYTHONPATH = if ($oldPath) {
        $testPath + [IO.Path]::PathSeparator + $oldPath
    } else { $testPath }
    $env:NSE_NATIVE_FAILURE_REPORT = [IO.Path]::GetFullPath($ReportPath)
    & uv run pytest tests/data_platform/test_native_failure_acceptance_report.py `
        tests/data_platform/test_native_failure_acceptance.py `
        -p native_failure_acceptance_report -q --tb=long
    if ($LASTEXITCODE -ne 0) { throw 'Focused native acceptance failed; report retained if created' }
    if (-not (Test-Path -LiteralPath $ReportPath -PathType Leaf)) {
        throw 'Focused acceptance report missing'
    }
    $report = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
    if ($report.suite_passed -ne $true -or $report.whole_platform_accepted -ne $false) {
        throw 'Focused acceptance report inconsistent; inspect without promoting eligibility'
    }
} finally {
    $env:PYTHONPATH = $oldPath
    $env:NSE_NATIVE_FAILURE_REPORT = $oldReport
}
$commands = @(
    @('run','pytest','tests/data_platform','-q'),
    @('run','pytest','tests','-q'),
    @('run','ruff','check','src/nse_quant/data_platform','scripts/inspect','scripts/ingest',
      'tests/data_platform'),
    @('run','mypy')
)
foreach ($arguments in $commands) {
    & uv @arguments
    if ($LASTEXITCODE -ne 0) { throw "QA failed: uv $arguments" }
}
& git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Tracked whitespace check failed' }
& uv run python -c "from pathlib import Path; import json; m=json.loads(Path('NATIVE_FAILURE_MANIFEST.json').read_text()); bad=[n for n in m if Path(n).is_file() and any(s.rstrip(' '+chr(9))!=s for s in Path(n).read_text(encoding='utf-8').splitlines())]; print(bad); raise SystemExit(bool(bad))"
if ($LASTEXITCODE -ne 0) { throw 'Payload whitespace check failed' }
Write-Output 'Focused acceptance and repository QA commands passed; production holds remain.'
