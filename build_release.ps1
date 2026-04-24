param(
    [string]$Python = "py -3",
    [string]$WorkPath = "release-build",
    [string]$DistPath = "release-dist"
)

$ErrorActionPreference = "Stop"

Write-Host "Cleaning previous build outputs..."
if (Test-Path $WorkPath) {
    Remove-Item -LiteralPath $WorkPath -Recurse -Force
}
if (Test-Path $DistPath) {
    Remove-Item -LiteralPath $DistPath -Recurse -Force
}

Write-Host "Installing dependencies..."
Invoke-Expression "$Python -m pip install -r requirements.txt"

Write-Host "Building windowed executable..."
Invoke-Expression "$Python -m PyInstaller --clean --noconfirm --workpath `"$WorkPath`" --distpath `"$DistPath`" iCloud_aio_tool.spec"

Write-Host "Build complete: $DistPath\\iCloud_aio_tool.exe"
