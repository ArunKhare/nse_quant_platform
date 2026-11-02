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
    $branch = & git branch --show-current
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect branch' }
    if ($branch.Trim() -ne 'feat/medallion-feature-store') { throw 'Unexpected branch' }
    $head = & git rev-parse HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect HEAD' }
    if ($head.Trim() -ne $ExpectedHead) { throw 'HEAD differs from reviewed full hash' }
    Invoke-Checked 'git' @('merge-base', '--is-ancestor', '9fffc70', 'HEAD')
    Invoke-Checked 'git' @('status', '--short')
    Write-Host ('Reviewed HEAD: ' + $head)
    $names = @()
    foreach ($line in Get-Content -LiteralPath 'RESEARCH_IV_CURRENT_STAGE_SHA256SUMS.txt') {
        if ($line -notmatch '^([a-f0-9]{64})  ([A-Za-z0-9_./-]+)$') { throw 'Invalid manifest' }
        $expected = $Matches[1]
        $relative = $Matches[2]
        if ($relative.StartsWith('/') -or $relative.Split('/') -contains '..') {
            throw 'Unsafe manifest path'
        }
        if ($names -contains $relative) { throw 'Duplicate payload path' }
        $names += $relative
        $actual = (Get-FileHash -LiteralPath $relative -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) { throw ('Changed payload: ' + $relative) }
    }
    if ($names.Count -ne 8) { throw 'Unexpected payload count' }
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
from nse_quant.data_platform import research_iv_first_stage as stage
from nse_quant.data_platform import research_iv_stage_record as record
from nse_quant.data_platform import research_iv_bundle_revalidation as native
assert stage.VERSION == 'audited-research-iv-first-stage@1'
assert record.VERSION == 'research-iv-first-stage-record@1' and record.MAX_RECORD_BYTES == 8192
assert native.VERSION == 'research-iv-bundle-current-source-revalidation@1'
'@
    Invoke-Checked 'uv' @('run', 'python', '-c', $runtime)
    Invoke-Checked 'uv' @('run', 'pytest',
        'tests/data_platform/test_research_iv_stage_observation.py',
        'tests/data_platform/test_research_iv_current_stage_boundary.py', '-q')
    Invoke-Checked 'uv' @('run', 'pytest', 'tests/data_platform', '-q')
    Invoke-Checked 'uv' @('run', 'pytest', 'tests', '-q')
    Invoke-Checked 'uv' @('run', 'ruff', 'check', 'src/nse_quant/data_platform',
        'scripts/inspect', 'scripts/ingest', 'tests/data_platform')
    Invoke-Checked 'uv' @('run', 'ruff', 'check', 'scripts/qa/verify_research_iv_current_stage_patch.py')
    Invoke-Checked 'uv' @('run', 'mypy')
    Invoke-Checked 'git' @('diff', '--check')
    $whitespace = @'
from pathlib import Path
manifest = Path('RESEARCH_IV_CURRENT_STAGE_SHA256SUMS.txt')
for line in manifest.read_text(encoding='utf-8').splitlines():
    path = Path(line.split('  ', 1)[1])
    raw = path.read_bytes()
    assert raw and raw.endswith(b'\n') and b'\r' not in raw, path
    assert all(s.rstrip(b' \t') == s for s in raw.splitlines()), path
print('Delivered payload whitespace checked, including untracked additions')
'@
    Invoke-Checked 'uv' @('run', 'python', '-c', $whitespace)
    Write-Host 'All runner commands passed locally; not full native platform acceptance.'
} finally { Pop-Location }
