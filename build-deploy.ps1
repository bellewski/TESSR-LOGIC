# Build customer deployment package for TESSR-LOGIC
# Run this to create a clean zip with no dev artifacts

$SourceDir = "C:\TESSR-LOGIC"
$DeployDir = "$env:TEMP\TESSR-LOGIC-Deploy"
$ZipPath = "$env:USERPROFILE\Desktop\TESSR-LOGIC-Deploy.zip"

Write-Host "Building deployment package..." -ForegroundColor Cyan

# Clean temp
if (Test-Path $DeployDir) { Remove-Item $DeployDir -Recurse -Force }
New-Item -ItemType Directory -Path $DeployDir | Out-Null

# Copy core files
$items = @(
    "backend",
    "frontend",
    "requirements.txt",
    "start.bat",
    "install-service.ps1",
    "service.py",
    "create-shortcut.ps1",
    "DEPLOY.md",
    "README.md"
)

foreach ($item in $items) {
    $src = Join-Path $SourceDir $item
    if (Test-Path $src) {
        Copy-Item $src "$DeployDir\" -Recurse -Force
        Write-Host "  + $item" -ForegroundColor Gray
    }
}

# Remove dev artifacts
$exclude = @(
    "__pycache__",
    "*.pyc",
    "node_modules",
    "dist",
    ".git",
    ".env",
    "*.db",
    "*.db-journal",
    "workspace\builds\*",
    "*.zip"
)

Write-Host "Cleaning dev artifacts..." -ForegroundColor Cyan
Get-ChildItem $DeployDir -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem $DeployDir -Recurse -Directory -Filter "node_modules" | Remove-Item -Recurse -Force
Get-ChildItem $DeployDir -Recurse -Directory -Filter ".git" | Remove-Item -Recurse -Force
Get-ChildItem $DeployDir -Recurse -Directory -Filter "dist" | Remove-Item -Recurse -Force
Get-ChildItem $DeployDir -Recurse -File -Filter "*.pyc" | Remove-Item -Force
Get-ChildItem $DeployDir -Recurse -File -Filter "*.db" | Remove-Item -Force
Get-ChildItem $DeployDir -Recurse -File -Filter "*.db-journal" | Remove-Item -Force

# Clean workspace build outputs but keep folder structure
$workspaceDir = "$DeployDir\workspace\builds"
if (Test-Path $workspaceDir) {
    Get-ChildItem $workspaceDir -Recurse | Remove-Item -Recurse -Force
}

# Remove old zip if exists
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

# Create zip using .NET (handles subdirectories correctly)
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($DeployDir, $ZipPath, "Optimal", $false)

$size = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
Write-Host ""
Write-Host "Deployment package created!" -ForegroundColor Green
Write-Host "Location: $ZipPath" -ForegroundColor Cyan
Write-Host "Size: $size MB" -ForegroundColor Cyan
Write-Host ""
Write-Host "Customer setup:" -ForegroundColor Yellow
Write-Host "  1. Unzip to any folder" -ForegroundColor Gray
Write-Host "  2. Right-click install-service.ps1 -> Run as Administrator" -ForegroundColor Gray
Write-Host "  3. Open http://localhost:8000" -ForegroundColor Gray
