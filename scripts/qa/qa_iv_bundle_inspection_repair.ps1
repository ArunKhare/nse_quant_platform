[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-f0-9]{40}$')]
    [string]$ExpectedHead,
    [string]$Repository = 'C:\Projects\nse_quant_platform'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)" }
}
Push-Location -LiteralPath $Repository
try {
    foreach ($line in Get-Content -LiteralPath 'IV_BUNDLE_INSPECTION_REPAIR_SHA256SUMS.txt') {
        if ($line -notmatch '^([a-f0-9]{64})  ([A-Za-z0-9_./-]+)$') { throw 'Invalid manifest' }
        $expected = $Matches[1]
        $relative = $Matches[2]
        if ($relative.StartsWith('/') -or $relative.Split('/') -contains '..') {
            throw 'Unsafe manifest path'
        }
        if ((Get-FileHash -LiteralPath $relative -Algorithm SHA256).Hash.ToLowerInvariant() `
            -ne $expected) { throw ('Changed repair payload: ' + $relative) }
    }
    Invoke-Checked 'uv' @('run', 'pytest',
        'tests/data_platform/test_iv_bundle_inspection_fixture_files.py', '-q')
    # Original runner checks actual branch/HEAD, interpreter/dependencies, original
    # payload hashes (two targeted test entries updated), and ALL mandatory QA.
    & '.\scripts\qa\qa_research_iv_bundle_inspection.ps1' `
        -Repository $Repository -ExpectedHead $ExpectedHead
    Invoke-Checked 'uv' @('run', 'ruff', 'check',
        'scripts/qa/repair_iv_bundle_inspection_tests.py',
        'scripts/qa/verify_iv_bundle_inspection_repair.py')
    $whitespace = @'
from pathlib import Path
manifest = Path('IV_BUNDLE_INSPECTION_REPAIR_SHA256SUMS.txt')
for line in manifest.read_text(encoding='utf-8').splitlines():
    path = Path(line.split('  ', 1)[1])
    raw = path.read_bytes()
    assert raw and raw.endswith(b'\n') and b'\r' not in raw, path
    assert all(s.rstrip(b' \t') == s for s in raw.splitlines()), path
'@
    Invoke-Checked 'uv' @('run', 'python', '-c', $whitespace)
} finally { Pop-Location }
