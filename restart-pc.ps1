<#
  Restart this PC (cleanly).
  - Optionally stops TESSR-LOGIC first (backend, frontend, Ollama)
  - Then restarts Windows after a cancellable countdown

  Usage:  right-click > Run with PowerShell   (or run restart-pc.bat)
    -Delay <sec>   countdown before restart (default 30)
    -Now           restart immediately (no countdown)
    -SkipStop      do NOT stop TESSR first
    -Force         skip the y/N confirmation prompt

  To CANCEL a pending restart at any time:  shutdown /a
#>
param(
    [int]$Delay = 30,
    [switch]$Now,
    [switch]$SkipStop,
    [switch]$Force
)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Restart PC" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# --- Confirm (unless -Force) --------------------------------------------
if (-not $Force) {
    $ans = Read-Host "This will RESTART your computer. Save your work. Continue? (y/N)"
    if ($ans -notin @("y", "Y", "yes", "Yes")) {
        Write-Host "Cancelled. Nothing was restarted." -ForegroundColor Yellow
        return
    }
}

# --- Stop TESSR cleanly first -------------------------------------------
if (-not $SkipStop) {
    $stop = Join-Path $Root "stop-tessr.ps1"
    if (Test-Path $stop) {
        Write-Host "[..] Stopping TESSR-LOGIC (backend, frontend, Ollama)..." -ForegroundColor Cyan
        try { & $stop } catch { Write-Host "[warn] stop-tessr had issues: $($_.Exception.Message)" -ForegroundColor Yellow }
    } else {
        Write-Host "[i] stop-tessr.ps1 not found - skipping clean stop" -ForegroundColor DarkGray
    }
}

if ($Now) { $Delay = 0 }

# --- Schedule the restart ------------------------------------------------
# shutdown.exe gives a built-in, abortable timer. Cancel with:  shutdown /a
Write-Host ""
Write-Host "[->] Restarting in $Delay second(s)..." -ForegroundColor Green
if ($Delay -gt 0) {
    Write-Host "     To CANCEL: open a terminal and run  shutdown /a" -ForegroundColor Yellow
}

shutdown.exe /r /t $Delay /c "TESSR-LOGIC: scheduled restart"
