param(
    [string]$TradeDate = (Get-Date -Format "yyyy-MM-dd")
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Python virtual environment not found: $Python"
    exit 1
}

# Run only on NSE trading days.
& $Python -c "from nse_quant.core.market_calendar import is_nse_trading_day; from datetime import date; raise SystemExit(0 if is_nse_trading_day(date.today()) else 2)"

if ($LASTEXITCODE -eq 2) {
    Write-Host "NSE market closed today. EOD maintenance skipped."
    exit 0
}

if ($LASTEXITCODE -ne 0) {
    Write-Error "Unable to determine NSE trading day."
    exit 1
}

$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$LogFile = Join-Path $LogDir "eod_maintenance_$Timestamp.log"

Write-Host "NSE Quant EOD maintenance"
Write-Host "Trade date: $TradeDate"
Write-Host "Log file:   $LogFile"

& $Python scripts/eod_maintenance.py --trade-date $TradeDate 2>&1 |
    Tee-Object -FilePath $LogFile

if ($LASTEXITCODE -ne 0) {
    Write-Error "EOD maintenance exited with code $LASTEXITCODE."
    exit $LASTEXITCODE
}

Write-Host "EOD maintenance completed."
