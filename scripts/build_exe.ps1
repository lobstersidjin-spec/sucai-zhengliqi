# Build 点点素材管理大师 to EXE
# Run from project root (sucai-zhengliqi)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projDir = Split-Path -Parent $scriptDir
Set-Location $projDir

# Install PyInstaller if needed
pip install pyinstaller ttkbootstrap -q

# Build (exe in dist/)
pyinstaller build.spec

# Copy exe to project folder as program entry
$exeSrc = Join-Path $projDir "dist\DiandianMaterialMaster.exe"
$exeDst = Join-Path $projDir "DiandianMaterialMaster.exe"
if (Test-Path $exeSrc) {
    Copy-Item $exeSrc $exeDst -Force
    Write-Host ""
    Write-Host "Build complete. DiandianMaterialMaster.exe created in project folder." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Build may have failed. Check dist\DiandianMaterialMaster.exe" -ForegroundColor Yellow
}
