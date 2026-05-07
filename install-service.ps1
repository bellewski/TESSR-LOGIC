# TESSR-LOGIC Windows Service Installer
# Run as Administrator: Right-click → "Run with PowerShell"

param(
    [switch]$Uninstall,
    [switch]$Start,
    [switch]$Stop
)

$ServiceName = "TESSR-LOGIC"
$DisplayName = "TESSR-LOGIC Multi-Agent Build System"
$Description = "Autonomous build pipeline with Architect, Coder, Validator, Builder, and SmokeTester agents."
$InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ExePath = "$InstallDir\python\pythonw.exe"
$ScriptPath = "$InstallDir\backend\main.py"
$LogPath = "$InstallDir\logs"

# Create logs directory
if (!(Test-Path $LogPath)) {
    New-Item -ItemType Directory -Path $LogPath -Force | Out-Null
}

# Check for admin privileges
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (!$isAdmin) {
    Write-Host "ERROR: Must run as Administrator" -ForegroundColor Red
    Write-Host "Right-click this script and select 'Run with PowerShell as administrator'"
    pause
    exit 1
}

function Install-NSSM {
    $nssmPath = "$InstallDir\nssm.exe"
    if (Test-Path $nssmPath) { return $nssmPath }
    
    Write-Host "Downloading NSSM (Non-Sucking Service Manager)..." -ForegroundColor Yellow
    $nssmZip = "$env:TEMP\nssm.zip"
    $nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
    
    try {
        Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip -UseBasicParsing
        Expand-Archive -Path $nssmZip -DestinationPath "$env:TEMP\nssm" -Force
        
        # Find the correct architecture
        $arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
        $nssmExe = Get-ChildItem -Path "$env:TEMP\nssm" -Recurse -Filter "nssm.exe" | Where-Object { $_.FullName -like "*$arch*" } | Select-Object -First 1
        
        if ($nssmExe) {
            Copy-Item $nssmExe.FullName -Destination $nssmPath -Force
            Remove-Item "$env:TEMP\nssm" -Recurse -Force -ErrorAction SilentlyContinue
            Remove-Item $nssmZip -Force -ErrorAction SilentlyContinue
            return $nssmPath
        }
    } catch {
        Write-Host "WARNING: Could not download NSSM automatically." -ForegroundColor Yellow
        Write-Host "Please download from https://nssm.cc and place nssm.exe in: $InstallDir" -ForegroundColor Yellow
        return $null
    }
}

function Install-Service {
    $nssm = Install-NSSM
    if (!$nssm -and !(Test-Path "$InstallDir\nssm.exe")) {
        Write-Host "ERROR: NSSM not found. Cannot create service." -ForegroundColor Red
        Write-Host "Options:"
        Write-Host "  1. Run 'pip install pywin32' and use install-pywin32-service.ps1 instead"
        Write-Host "  2. Manually download nssm.exe to $InstallDir"
        pause
        exit 1
    }
    if (!$nssm) { $nssm = "$InstallDir\nssm.exe" }
    
    # Check if service exists
    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Service already exists. Removing old service first..." -ForegroundColor Yellow
        & $nssm remove $ServiceName confirm
    }
    
    # Build the command
    $pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (!$pythonExe) {
        $pythonExe = "$InstallDir\venv\Scripts\python.exe"
        if (!(Test-Path $pythonExe)) {
            Write-Host "ERROR: Python not found in PATH and no venv detected" -ForegroundColor Red
            pause
            exit 1
        }
    }
    
    $envVars = "PYTHONPATH=$InstallDir\backend\.."
    $workingDir = $InstallDir
    
    Write-Host "Installing TESSR-LOGIC as Windows service..." -ForegroundColor Green
    
    & $nssm install $ServiceName $pythonExe "-m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --no-access-log"
    & $nssm set $ServiceName DisplayName $DisplayName
    & $nssm set $ServiceName Description $Description
    & $nssm set $ServiceName Application $pythonExe
    & $nssm set $ServiceName AppParameters "-m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --no-access-log"
    & $nssm set $ServiceName AppDirectory $workingDir
    & $nssm set $ServiceName AppEnvironmentExtra $envVars
    & $nssm set $ServiceName Start SERVICE_AUTO_START
    & $nssm set $ServiceName ObjectName "LocalSystem"
    & $nssm set $ServiceName Stdout "$LogPath\service-out.log"
    & $nssm set $ServiceName Stderr "$LogPath\service-err.log"
    
    Write-Host "Service installed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Service will auto-start on boot." -ForegroundColor Cyan
    Write-Host "Access the app at: http://localhost:8000" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  Start:   net start $ServiceName"
    Write-Host "  Stop:    net stop $ServiceName"
    Write-Host "  Remove:  .\$($MyInvocation.MyCommand.Name) -Uninstall"
    Write-Host ""
    
    # Start immediately
    Start-Service -Name $ServiceName
    Write-Host "Service started!" -ForegroundColor Green
}

function Remove-Service {
    $nssm = "$InstallDir\nssm.exe"
    if (Test-Path $nssm) {
        Stop-Service -Name $ServiceName -ErrorAction SilentlyContinue
        & $nssm remove $ServiceName confirm
        Write-Host "Service removed." -ForegroundColor Green
    } else {
        # Try sc.exe fallback
        sc.exe stop $ServiceName | Out-Null
        sc.exe delete $ServiceName | Out-Null
        Write-Host "Service removed (using sc.exe)." -ForegroundColor Green
    }
}

# Main
if ($Uninstall) {
    Remove-Service
} elseif ($Stop) {
    Stop-Service -Name $ServiceName
    Write-Host "Service stopped." -ForegroundColor Green
} elseif ($Start) {
    Start-Service -Name $ServiceName
    Write-Host "Service started." -ForegroundColor Green
} else {
    Install-Service
}

pause
