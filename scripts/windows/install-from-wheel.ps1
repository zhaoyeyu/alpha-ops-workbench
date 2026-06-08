Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Resolve-Path "$PSScriptRoot\..\.."
$Wheel = Get-ChildItem -Path (Join-Path $Root "dist") -Filter "alphaops_workbench-*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $Wheel) {
    throw "No wheel found under dist/. Run: python -m build"
}

python -m pip install --force-reinstall --no-deps $Wheel.FullName
alphaops doctor
alphaops smoke
