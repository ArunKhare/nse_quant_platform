param(
    [Parameter(Mandatory=$true)][string]$SourceDb,
    [Parameter(Mandatory=$true)][string]$TradeDate,
    [string]$Symbol = "NIFTY",
    [string]$CodeRevision = "",
    [string]$RunRoot = "data/workflow_runs",
    [string[]]$CandleIntervals = @('5m', '15m', '30m', '60m'),
    [switch]$Execute,
    [switch]$SourceOffline
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Virtual environment Python is missing" }
$Arguments = @(
    "scripts/eod_maintenance.py", "--source-db", $SourceDb,
    "--trade-date", $TradeDate, "--symbol", $Symbol,
    "--run-root", $RunRoot, "--candle-intervals", ($CandleIntervals -join ',')
)
if ($Execute) {
    if (-not $SourceOffline -or [string]::IsNullOrWhiteSpace($CodeRevision)) {
        throw "Execution requires -SourceOffline and -CodeRevision"
    }
    & $Python -c "from nse_quant.core.market_calendar import is_nse_trading_day; from datetime import date; import sys; raise SystemExit(0 if is_nse_trading_day(date.fromisoformat(sys.argv[1])) else 2)" $TradeDate
    if ($LASTEXITCODE -eq 2) { Write-Host "Non-trading date; execution skipped"; exit 0 }
    if ($LASTEXITCODE -ne 0) { throw "Trading-calendar check failed" }
    $Arguments += @("--execute", "--source-offline", "--code-revision", $CodeRevision)
}
& $Python @Arguments
exit $LASTEXITCODE
