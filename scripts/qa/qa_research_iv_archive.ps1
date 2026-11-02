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
    Invoke-Checked git @('show', '--no-patch', '--format=%H%n%P%n%s', 'HEAD')
    Invoke-Checked git @('merge-base', '--is-ancestor', '7fa0168', 'HEAD')
    Invoke-Checked git @('status', '--short')
    Invoke-Checked uv @('run', 'python', '-c', 'import sys, scipy; print(sys.version); print("SciPy", scipy.__version__); assert sys.version_info >= (3,12); assert tuple(int(x) for x in scipy.__version__.split(".")[:2]) >= (1,14); from nse_quant.data_platform import native_research_option as n; assert n.VERSION == "native-gold-research-iv-candidate@1"')
    Invoke-Checked uv @('run', 'pytest', 'tests/data_platform/test_research_iv_record.py',
        'tests/data_platform/test_research_iv_archive_sql.py',
        'tests/data_platform/test_research_iv_store_boundary.py', '-q')
    Invoke-Checked uv @('run', 'pytest', 'tests/data_platform', '-q')
    Invoke-Checked uv @('run', 'pytest', 'tests', '-q')
    Invoke-Checked uv @('run', 'ruff', 'check', 'src/nse_quant/data_platform',
        'scripts/inspect', 'scripts/ingest', 'tests/data_platform')
    Invoke-Checked uv @('run', 'mypy')
    Invoke-Checked git @('diff', '--check')
} finally { Pop-Location }
