param(
    [string]$IsccPath = "",
    [string]$AppVersion = "1.0.0",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($AppVersion -match "\s") {
    throw "AppVersion cannot contain spaces. Example: -AppVersion alpha-1.0"
}

if ($Clean) {
    if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
    if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }
}

# Prevent common lock issue when app is running from dist/BimmerDaten.
$distExe = Join-Path $root "dist\BimmerDaten\BimmerDaten.exe"
if (Test-Path $distExe) {
    $running = Get-Process -Name "BimmerDaten" -ErrorAction SilentlyContinue
    if ($running) {
        throw "BimmerDaten.exe is running and can lock dist files. Close the app and rerun the script."
    }
}

Write-Host "[1/2] Building app with PyInstaller..."
pyinstaller --noconfirm BimmerDaten.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

if (-not $IsccPath) {
    $possible = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    foreach ($p in $possible) {
        if (Test-Path $p) {
            $IsccPath = $p
            break
        }
    }
}

if (-not $IsccPath -or -not (Test-Path $IsccPath)) {
    throw "ISCC.exe not found. Install Inno Setup 6 or pass -IsccPath."
}

Write-Host "[2/2] Building installer with Inno Setup..."
& $IsccPath "/DMyAppVersion=$AppVersion" "installer\BimmerDaten.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup (ISCC) failed with exit code $LASTEXITCODE"
}

$setupExe = Join-Path $root "installer\output\BimmerDaten-Setup.exe"
if (-not (Test-Path $setupExe)) {
    throw "Installer output not found: $setupExe"
}

$hash = Get-FileHash -Algorithm SHA256 -Path $setupExe
$hashFile = "$setupExe.sha256"
"$($hash.Hash)  $(Split-Path -Leaf $setupExe)" | Set-Content -Path $hashFile -Encoding ascii

Write-Host "SHA256: $($hash.Hash)"
Write-Host "SHA256 file: $hashFile"

Write-Host "Done. Installer should be in installer\output\."
