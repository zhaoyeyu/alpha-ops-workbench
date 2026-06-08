Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location (Resolve-Path "$PSScriptRoot\..\..")
try {
    python -m pip install -e ".[dev]"
    alphaops doctor
} finally {
    Pop-Location
}
