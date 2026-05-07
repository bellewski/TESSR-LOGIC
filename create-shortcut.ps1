# TESSR-LOGIC Desktop Shortcut Creator
# Run as normal user (no admin needed)

$WshShell = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath("Desktop")
$InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Create shortcut
$Shortcut = $WshShell.CreateShortcut("$Desktop\TESSR-LOGIC.lnk")
$Shortcut.TargetPath = "http://localhost:8000"
$Shortcut.IconLocation = "%SystemRoot%\System32\shell32.dll,14"
$Shortcut.Description = "TESSR-LOGIC Multi-Agent Build System"
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Save()

Write-Host "✅ TESSR-LOGIC shortcut created on your Desktop" -ForegroundColor Green
Write-Host "   Double-click 'TESSR-LOGIC' to open in your browser" -ForegroundColor Cyan
Write-Host ""
Write-Host "The app runs automatically as a service when Windows starts." -ForegroundColor Gray

pause
