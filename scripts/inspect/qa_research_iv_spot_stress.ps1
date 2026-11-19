param(
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^[a-f0-9]{40}$')]
    [string]$ExpectedHead
)
$ErrorActionPreference = 'Stop'
function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Program" }
}
$head = (& git rev-parse HEAD)
if ($LASTEXITCODE -ne 0 -or $head -cne $ExpectedHead) { throw 'Reviewed full HEAD mismatch' }
$branch = (& git branch --show-current)
if ($LASTEXITCODE -ne 0 -or $branch -cne 'feat/medallion-feature-store') {
    throw 'Unexpected branch'
}
Invoke-Checked 'uv' @('run','python','-c','import sys; print(sys.executable); print(sys.version)')
Invoke-Checked 'uv' @('run','pytest','tests/data_platform','-q')
Invoke-Checked 'uv' @('run','pytest','tests','-q')
Invoke-Checked 'uv' @('run','ruff','check','src/nse_quant/data_platform','scripts/inspect','scripts/ingest','tests/data_platform')
Invoke-Checked 'uv' @('run','ruff','check','verify_research_iv_spot_stress_zip.py')
Invoke-Checked 'uv' @('run','mypy')
Invoke-Checked 'git' @('diff','--check')
Invoke-Checked 'git' @('diff','--cached','--check')
Invoke-Checked 'uv' @('run','python','-c', 'import pathlib,subprocess; names=subprocess.check_output(["git","ls-files","--others","--exclude-standard","-z"]).decode().split(chr(0)); bad=[n for n in names if n and pathlib.Path(n).suffix in (".py",".md",".ps1") and any(line.rstrip(b" \t")!=line for line in pathlib.Path(n).read_bytes().splitlines())]; print(bad); raise SystemExit(bool(bad))')
