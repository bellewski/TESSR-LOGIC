<#
  TESSR-LOGIC shutdown
  - Stops the backend (:8000) and frontend (:5173)
  - Stops Ollama so no LLM keeps running and VRAM is freed
  - Verifies the ports are closed

  Usage:  right-click > Run with PowerShell   (or run stop-tessr.bat)
          optional flag:  -KeepOllama   (leave Ollama running)
#>
param(
    [switch]$KeepOllama
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TESSR-LOGIC shutdown" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

function Stop-Port($port, $label) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { Write-Host "[ok] :$port already free ($label)" -ForegroundColor DarkGray; return }
    $pids = $conns.OwningProcess | Select-Object -Unique
    foreach ($procId in $pids) {
        if (-not $procId) { continue }
        $name = (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Write-Host "[ok] stopped $label on :$port  (PID $procId $name)" -ForegroundColor Green
        } catch {
            Write-Host "[warn] could not stop PID $procId on :$port - $($_.Exception.Message)" -ForegroundColor Yellow
            Write-Host "       (it may be elevated; close its window manually)" -ForegroundColor DarkGray
        }
    }
}

# --- Backend / frontend by port ------------------------------------------
Stop-Port 8000 "backend"
Stop-Port 5173 "frontend"

# --- Catch stray uvicorn / vite processes by command line ----------------
try {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'backend.main' } |
        ForEach-Object {
            try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host "[ok] stopped stray backend (PID $($_.ProcessId))" -ForegroundColor Green } catch {}
        }
} catch {}
try {
    Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'vite' } |
        ForEach-Object {
            try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host "[ok] stopped stray frontend (PID $($_.ProcessId))" -ForegroundColor Green } catch {}
        }
} catch {}

# --- Ollama (frees VRAM) -------------------------------------------------
if ($KeepOllama) {
    Write-Host "[i] -KeepOllama: leaving Ollama running" -ForegroundColor Cyan
} else {
    $ollama = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like 'ollama*' }
    if (-not $ollama) {
        Write-Host "[ok] Ollama not running" -ForegroundColor DarkGray
    } else {
        foreach ($p in $ollama) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction Stop; Write-Host "[ok] stopped Ollama process ($($p.ProcessName), PID $($p.Id))" -ForegroundColor Green }
            catch { Write-Host "[warn] could not stop $($p.ProcessName) PID $($p.Id) - $($_.Exception.Message)" -ForegroundColor Yellow }
        }
    }
}

Start-Sleep -Seconds 2

# --- Verify --------------------------------------------------------------
Write-Host ""
Write-Host "--- verification ---" -ForegroundColor Cyan
$b = (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
$f = (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)
$o = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like 'ollama*' }
Write-Host ("  :8000 backend  : " + $(if ($b) { "STILL OPEN" } else { "closed" })) -ForegroundColor $(if ($b) { "Yellow" } else { "Green" })
Write-Host ("  :5173 frontend : " + $(if ($f) { "STILL OPEN" } else { "closed" })) -ForegroundColor $(if ($f) { "Yellow" } else { "Green" })
if (-not $KeepOllama) {
    Write-Host ("  Ollama         : " + $(if ($o) { "STILL RUNNING" } else { "stopped" })) -ForegroundColor $(if ($o) { "Yellow" } else { "Green" })
}

if ($b -or $f -or (-not $KeepOllama -and $o)) {
    Write-Host ""
    Write-Host "Some processes survived (likely started in an elevated/Administrator window)." -ForegroundColor Yellow
    Write-Host "Re-run this script as Administrator, or close those windows manually." -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "All stopped. Ports free and no LLM running." -ForegroundColor Green
}
