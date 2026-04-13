param(
    [string]$IsccPath = "",
    [string]$AppVersion = "1.0.0",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($Clean) {
    if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
    if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }
}

Write-Host "[1/2] Building app with PyInstaller..."
pyinstaller BimmerDaten.spec

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

Write-Host "Done. Installer should be in installer\output\."
