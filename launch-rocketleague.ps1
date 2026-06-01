<#
  Launch Steam (if not already running) and start Rocket League.
  Rocket League Steam App ID = 252950
#>
$appId = 252950

Write-Host "Launching Rocket League via Steam..." -ForegroundColor Cyan

# --- Locate steam.exe ----------------------------------------------------
$steamExe = $null
$steamPath = (Get-ItemProperty -Path 'HKCU:\Software\Valve\Steam' -Name SteamPath -ErrorAction SilentlyContinue).SteamPath
if ($steamPath) {
    $candidate = Join-Path $steamPath 'steam.exe'
    if (Test-Path $candidate) { $steamExe = $candidate }
}
if (-not $steamExe) {
    foreach ($p in @("${env:ProgramFiles(x86)}\Steam\steam.exe", "$env:ProgramFiles\Steam\steam.exe")) {
        if (Test-Path $p) { $steamExe = $p; break }
    }
}

# --- Start Steam if it isn't running -------------------------------------
if (Get-Process -Name steam -ErrorAction SilentlyContinue) {
    Write-Host "[ok] Steam already running" -ForegroundColor Green
} elseif ($steamExe) {
    Write-Host "[..] Starting Steam: $steamExe" -ForegroundColor Cyan
    Start-Process $steamExe
    Write-Host "[..] Waiting for Steam to come up..." -ForegroundColor Cyan
    Start-Sleep -Seconds 8
} else {
    Write-Host "[i] Could not find steam.exe - relying on the steam:// protocol to start it." -ForegroundColor Yellow
}

# --- Launch Rocket League ------------------------------------------------
Write-Host "[->] Launching Rocket League (app $appId)" -ForegroundColor Green
Start-Process "steam://rungameid/$appId"
