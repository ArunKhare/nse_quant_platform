param([Parameter(Mandatory=$true)][string]$ExpectedHead)
$ErrorActionPreference = 'Stop'
if ($ExpectedHead -cnotmatch '^[0-9a-f]{40}$') { throw 'Full reviewed local HEAD required' }
$head = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $head -cne $ExpectedHead) { throw 'HEAD mismatch' }
& git status --short
& git branch --show-current
& uv run python -c "import sys; print(sys.executable); print(sys.version)"
if ($LASTEXITCODE -ne 0) { throw 'Interpreter check failed' }
$commands = @(
    @('run','pytest','tests/data_platform/test_native_acceptance_slice.py','-q'),
    @('run','pytest','tests/data_platform','-q'),
    @('run','pytest','tests','-q'),
    @('run','ruff','check','src/nse_quant/data_platform','scripts/inspect','scripts/ingest',
      'tests/data_platform'),
    @('run','mypy')
)
foreach ($arguments in $commands) {
    & uv @arguments
    if ($LASTEXITCODE -ne 0) { throw "QA command failed: uv $arguments" }
}
& git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Tracked whitespace check failed' }
& uv run python -c "import pathlib,subprocess; names=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z']).decode().split(chr(0)); bad=[n for n in names if n and pathlib.Path(n).is_file() and pathlib.Path(n).suffix in {'.py','.md','.ps1'} and any(x.rstrip(' '+chr(9))!=x for x in pathlib.Path(n).read_text(encoding='utf-8').splitlines())]; print(bad); raise SystemExit(bool(bad))"
if ($LASTEXITCODE -ne 0) { throw 'Untracked whitespace check failed' }
