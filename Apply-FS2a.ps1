param([string]$Repository = "C:\Projects\nse_quant_platform")
$ErrorActionPreference = "Stop"
$Patch = Join-Path $PSScriptRoot "fs2a.patch"
Push-Location $Repository
try {
    $Branch = git branch --show-current
    if ($LASTEXITCODE -ne 0 -or $Branch -ne "feat/medallion-feature-store") {
        throw "Expected feat/medallion-feature-store; refusing application."
    }
    $Dirty = git status --porcelain
    if ($LASTEXITCODE -ne 0 -or $Dirty) { throw "Clean worktree required." }
    git apply --check -- $Patch
    if ($LASTEXITCODE -ne 0) { throw "Patch check failed; no files applied." }
    git apply -- $Patch
    if ($LASTEXITCODE -ne 0) { throw "Application failed; inspect git status." }
    git status --short
    Write-Host "Applied additive files only. Run local QA before commit."
} finally { Pop-Location }
