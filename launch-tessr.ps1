<#
  TESSR-LOGIC launcher
  - Starts the FastAPI backend (port 8000) in its own window
  - Starts the Vite frontend dev server (port 5173) in its own window
  - Waits for both to be reachable, then opens the website in your browser

  Usage:  right-click > Run with PowerShell   (or run TESSR-LOGIC.bat)
          optional flags:  -Prod   (serve built frontend from the backend on :8000 only)
                           -NoBrowser
#>
param(
    [switch]$Prod,
    [switch]$NoBrowser,
    [switch]$Monitor,            # after launch, keep showing live LLM + pipeline health
    [int]$MonitorInterval = 5    # seconds between refreshes in -Monitor mode
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $Root

function Test-Port($port) {
    # Quiet TCP check (no ICMP/progress noise from Test-NetConnection)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect('127.0.0.1', $port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(800)
        if ($ok -and $client.Connected) { $client.EndConnect($iar); $client.Close(); return $true }
        $client.Close(); return $false
    } catch { return $false }
}

function Wait-ForUrl($url, $timeoutSec = 60) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $timeoutSec) {
        try {
            Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 | Out-Null
            return $true
        } catch { Start-Sleep -Milliseconds 800 }
    }
    return $false
}

function Get-Json($url, $timeoutSec = 4) {
    try { return Invoke-RestMethod -Uri $url -TimeoutSec $timeoutSec } catch { return $null }
}

function Show-Health {
    param([switch]$Once)
    do {
        if (-not $Once) { Clear-Host }
        Write-Host "===== TESSR-LOGIC health =====  $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Cyan

        # --- Backend ---
        $health = Get-Json "http://localhost:8000/api/health"
        if ($health) { Write-Host "  Backend  : UP (:8000)" -ForegroundColor Green }
        else { Write-Host "  Backend  : DOWN" -ForegroundColor Red }

        # --- LLM / Ollama health (via backend, falls back to direct + ps) ---
        $oll = Get-Json "http://localhost:8000/api/ollama/health" 6
        $connected = $oll -and ($oll.connected -or $oll.status -eq 'ok')
        $busy = $false
        if (-not $connected) {
            # The health ping may have just timed out because Ollama is BUSY generating.
            # Confirm it's actually up via a direct call / a loaded model before crying down.
            $direct = Get-Json "http://localhost:11434/api/tags" 6
            $hasModel = $false
            try { if ((& ollama ps 2>$null | Select-Object -Skip 1 | Where-Object { $_.Trim() })) { $hasModel = $true } } catch {}
            if ($direct -or $hasModel) { $connected = $true; $busy = $true }
        }
        if ($connected -and $busy) { Write-Host "  LLM      : CONNECTED (busy generating)" -ForegroundColor Green }
        elseif ($connected) { Write-Host "  LLM      : CONNECTED (Ollama reachable)" -ForegroundColor Green }
        else { Write-Host "  LLM      : UNREACHABLE - run 'ollama serve'" -ForegroundColor Yellow }

        # --- Loaded model + GPU/CPU split (proves the LLM is actually engaged) ---
        $ps = $null
        try { $ps = (& ollama ps 2>$null) } catch {}
        if ($ps) {
            $lines = $ps | Select-Object -Skip 1 | Where-Object { $_.Trim() }
            if ($lines) {
                foreach ($l in $lines) { Write-Host "  Model    : $($l.Trim())" -ForegroundColor Green }
            } else {
                Write-Host "  Model    : none loaded (idle - loads on first build call)" -ForegroundColor DarkGray
            }
        }

        # --- Pipeline activity: is a build running, and which phase? ---
        $builds = Get-Json "http://localhost:8000/api/builds?skip=0&limit=10"
        $list = if ($builds.builds) { $builds.builds } else { $builds }
        $running = @($list | Where-Object { $_.status -eq 'running' })
        if ($running.Count -gt 0) {
            foreach ($b in $running) {
                $phase = if ($b.current_phase) { $b.current_phase } else { $b.phase }
                Write-Host "  Pipeline : WORKING -> '$($b.project_name)' [phase: $phase]" -ForegroundColor Green
            }
            if ($connected) { Write-Host "  Status   : LLM is actively working through the pipeline." -ForegroundColor Green }
        } else {
            Write-Host "  Pipeline : idle (no build running)" -ForegroundColor DarkGray
        }

        if (-not $Once) {
            Write-Host ""
            Write-Host "Refreshing every $MonitorInterval s. Press Ctrl+C to stop monitoring (servers keep running)." -ForegroundColor DarkGray
            Start-Sleep -Seconds $MonitorInterval
        }
    } while (-not $Once)
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TESSR-LOGIC launcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# --- Prerequisite checks -------------------------------------------------
try { python --version | Out-Null } catch { Write-Host "ERROR: Python not found in PATH." -ForegroundColor Red; Read-Host "Press Enter to exit"; exit 1 }

# Ollama (optional but needed for builds)
try {
    Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 3 | Out-Null
    Write-Host "[ok] Ollama is running" -ForegroundColor Green
} catch {
    Write-Host "[warn] Ollama not reachable on :11434 - builds will fail until you run 'ollama serve'" -ForegroundColor Yellow
}

# --- Env file ------------------------------------------------------------
$envArg = ""
if (Test-Path (Join-Path $Root ".env")) { $envArg = "--env-file .env" }

# --- Start backend -------------------------------------------------------
if (Test-Port 8000) {
    Write-Host "[ok] Backend already running on :8000" -ForegroundColor Green
} else {
    Write-Host "[..] Starting backend on :8000" -ForegroundColor Cyan
    $backendCmd = "Set-Location '$Root'; python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 $envArg"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd -WindowStyle Normal
}

# --- Start frontend (dev) unless -Prod -----------------------------------
$siteUrl = "http://localhost:8000"
if (-not $Prod) {
    if (Test-Port 5173) {
        Write-Host "[ok] Frontend dev already running on :5173" -ForegroundColor Green
    } else {
        Write-Host "[..] Starting frontend dev on :5173" -ForegroundColor Cyan
        if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) {
            Write-Host "[..] Installing frontend deps (first run)..." -ForegroundColor Yellow
            Push-Location (Join-Path $Root "frontend"); npm install | Out-Null; Pop-Location
        }
        $frontendCmd = "Set-Location '$Root\frontend'; npm run dev"
        Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd -WindowStyle Normal
    }
    $siteUrl = "http://localhost:5173"
} else {
    Write-Host "[i] -Prod: backend serves the built frontend on :8000" -ForegroundColor Cyan
}

# --- Wait for readiness --------------------------------------------------
Write-Host "[..] Waiting for backend..." -ForegroundColor Cyan
if (Wait-ForUrl "http://localhost:8000/api/health" 90) { Write-Host "[ok] Backend up" -ForegroundColor Green }
else { Write-Host "[warn] Backend did not respond in time (check its window)" -ForegroundColor Yellow }

if (-not $Prod) {
    Write-Host "[..] Waiting for frontend..." -ForegroundColor Cyan
    if (Wait-ForUrl $siteUrl 90) { Write-Host "[ok] Frontend up" -ForegroundColor Green }
    else { Write-Host "[warn] Frontend did not respond in time (check its window)" -ForegroundColor Yellow }
}

# --- Open the website ----------------------------------------------------
if (-not $NoBrowser) {
    Write-Host "[->] Opening $siteUrl" -ForegroundColor Green
    Start-Process $siteUrl
}

Write-Host ""
Write-Host "TESSR-LOGIC is running:" -ForegroundColor Cyan
Write-Host "  Website : $siteUrl"
Write-Host "  Backend : http://localhost:8000  (API docs: /docs)"
Write-Host "Close the two PowerShell windows (or run stop-tessr.bat) to stop the servers." -ForegroundColor DarkGray

# --- LLM + pipeline health ----------------------------------------------
Write-Host ""
Show-Health -Once

if ($Monitor) {
    Write-Host ""
    Write-Host "[Monitor] Live LLM + pipeline health (Ctrl+C to stop)..." -ForegroundColor Cyan
    Start-Sleep -Seconds 2
    Show-Health
} else {
    Write-Host ""
    Write-Host "Tip: run with -Monitor for a live LLM/pipeline status panel." -ForegroundColor DarkGray
}
