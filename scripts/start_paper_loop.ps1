param(
    [string]$EndTime = "15:50"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Python virtual environment not found: $Python"
    exit 1
}

# Skip weekends and NSE trading holidays.
& $Python -c "from nse_quant.core.market_calendar import is_nse_trading_day; from datetime import date; raise SystemExit(0 if is_nse_trading_day(date.today()) else 2)"

if ($LASTEXITCODE -eq 2) {
    Write-Host "NSE market closed today. Paper loop not started."
    exit 0
}

if ($LASTEXITCODE -ne 0) {
    Write-Error "Unable to determine NSE trading day."
    exit 1
}

# Fail closed if the persistent kill switch is active.
& $Python -c "from nse_quant.ops.kill_switch import KillSwitch; raise SystemExit(1 if KillSwitch().is_active() else 0)"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Persistent kill switch is active. Paper loop not started."
    exit 1
}

$Today = Get-Date -Format "yyyy-MM-dd"
$StopAt = Get-Date "$Today $EndTime"

$Now = Get-Date

if ($Now -ge $StopAt) {
    Write-Host "Requested end time has passed. Paper loop not started."
    exit 0
}

$Seconds = [int][math]::Ceiling(($StopAt - $Now).TotalSeconds)

$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$LogFile = Join-Path $LogDir "paper_loop_$Timestamp.log"

Write-Host "NSE Quant paper loop"
Write-Host "Start:      $($Now.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "Stop:       $($StopAt.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "Duration:   $Seconds seconds"
Write-Host "Log file:   $LogFile"

& $Python scripts/run_paper_loop.py --seconds $Seconds 2>&1 |
    Tee-Object -FilePath $LogFile

if ($LASTEXITCODE -ne 0) {
    Write-Error "Paper loop exited with code $LASTEXITCODE."
    exit $LASTEXITCODE
}

Write-Host "Paper loop completed."
