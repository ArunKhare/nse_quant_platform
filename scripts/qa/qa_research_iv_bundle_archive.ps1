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
    Write-Host ('> ' + $Program + ' ' + ($Arguments -join ' '))
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)" }
}

Push-Location -LiteralPath $Repository
try {
    $branch = & git branch --show-current
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect branch' }
    if ($branch.Trim() -ne 'feat/medallion-feature-store') { throw 'Unexpected branch' }
    $head = & git rev-parse HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect HEAD' }
    if ($head.Trim() -ne $ExpectedHead) { throw 'HEAD differs from explicitly reviewed HEAD' }
    Invoke-Checked 'git' @('status', '--short')
    Write-Host ('Reviewed HEAD: ' + $head)
    $manifest = 'RESEARCH_IV_BUNDLE_ARCHIVE_SHA256SUMS.txt'
    foreach ($line in Get-Content -LiteralPath $manifest) {
        if ($line -notmatch '^([a-f0-9]{64})  ([A-Za-z0-9_./-]+)$') {
            throw 'Malformed payload checksum manifest'
        }
        $expected = $Matches[1]
        $relative = $Matches[2]
        if ($relative.StartsWith('/') -or $relative.Split('/') -contains '..') {
            throw 'Unsafe manifest path'
        }
        if (-not (Test-Path -LiteralPath $relative -PathType Leaf)) {
            throw ('Missing payload: ' + $relative)
        }
        $actual = (Get-FileHash -LiteralPath $relative -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) { throw ('Payload changed: ' + $relative) }
    }
    $runtime = @'
import importlib.metadata as m
import sys
import tomllib
from pathlib import Path
assert sys.version_info >= (3, 12)
p = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
assert p['project']['requires-python'] == '>=3.12'
for bound in ('scipy>=1.14.0', 'cryptography>=46.0.0'):
    assert bound in p['project']['dependencies'], bound
for name, minimum in (('scipy', (1, 14, 0)), ('cryptography', (46, 0, 0))):
    version = m.version(name)
    core = version.split('+')[0].split('.')
    assert len(core) >= 3 and all(x.isdigit() for x in core[:3]), (name, version)
    assert tuple(map(int, core[:3])) >= minimum, (name, version)
    print(name, version)
print('uv interpreter:', sys.executable)
print('uv Python:', sys.version)
from nse_quant.data_platform import research_iv_bundle as codec
from nse_quant.data_platform import native_research_iv_bundle as native
from nse_quant.data_platform import research_iv_revalidation as current
from nse_quant.data_platform import research_iv_store as archive
assert codec.VERSION == 'research-iv-feature-bundle@1'
assert native.VERSION == 'native-research-iv-bundle-assembly@1'
assert current.VERSION == 'research-iv-current-source-revalidation@1'
assert archive.VERSION == 'audited-research-iv-builds@1'
'@
    Invoke-Checked 'uv' @('run', 'python', '-c', $runtime)
    # First close the previously delivered, locally unconfirmed dependency package.
    Invoke-Checked 'uv' @('run', 'pytest',
        'tests/data_platform/test_research_iv_bundle.py',
        'tests/data_platform/test_native_research_iv_bundle_boundary.py', '-q')
    Invoke-Checked 'uv' @('run', 'pytest',
        'tests/data_platform/test_research_iv_bundle_archive_record.py',
        'tests/data_platform/test_research_iv_bundle_store_boundary.py', '-q')
    Invoke-Checked 'uv' @('run', 'pytest', 'tests/data_platform', '-q')
    Invoke-Checked 'uv' @('run', 'pytest', 'tests', '-q')
    Invoke-Checked 'uv' @('run', 'ruff', 'check', 'src/nse_quant/data_platform',
        'scripts/inspect', 'scripts/ingest', 'tests/data_platform')
    Invoke-Checked 'uv' @('run', 'mypy')
    Invoke-Checked 'git' @('diff', '--check')
    $whitespace = @'
from pathlib import Path
manifest = Path('RESEARCH_IV_BUNDLE_ARCHIVE_SHA256SUMS.txt')
for line in manifest.read_text(encoding='utf-8').splitlines():
    relative = line.split('  ', 1)[1]
    raw = Path(relative).read_bytes()
    assert raw and raw.endswith(b'\n'), relative
    assert b'\r' not in raw, relative
    assert all(x.rstrip(b' \t') == x for x in raw.splitlines()), relative
print('Added payload whitespace checked, including untracked additions')
'@
    Invoke-Checked 'uv' @('run', 'python', '-c', $whitespace)
    Write-Host 'All commands in this runner completed successfully in this repository.'
    Write-Host 'This is not full native integrated/operational platform acceptance.'
} finally {
    Pop-Location
}
