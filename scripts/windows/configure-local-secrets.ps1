param(
    [string]$MassiveApiKey,
    [string]$AlpacaApiKeyId,
    [string]$AlpacaApiSecretKey,
    [string]$OpenRouterPrimaryKey,
    [string]$OpenRouterSecondaryKey
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Resolve-Path "$PSScriptRoot\..\.."
$ExamplePath = Join-Path $Root ".env.example"
$EnvPath = Join-Path $Root ".env"

if (-not (Test-Path -LiteralPath $EnvPath)) {
    Copy-Item -LiteralPath $ExamplePath -Destination $EnvPath
}

$values = [ordered]@{
    "MASSIVE_API_KEY" = $MassiveApiKey
    "ALPACA_API_KEY_ID" = $AlpacaApiKeyId
    "ALPACA_API_SECRET_KEY" = $AlpacaApiSecretKey
    "OPENROUTER_API_KEY_PRIMARY" = $OpenRouterPrimaryKey
    "OPENROUTER_API_KEY_SECONDARY" = $OpenRouterSecondaryKey
}

$lines = Get-Content -LiteralPath $EnvPath -Encoding UTF8
foreach ($entry in $values.GetEnumerator()) {
    if ([string]::IsNullOrWhiteSpace($entry.Value)) {
        continue
    }
    $prefix = "$($entry.Key)="
    $replacement = "$prefix$($entry.Value)"
    $index = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].StartsWith($prefix)) {
            $index = $i
            break
        }
    }
    if ($index -ge 0) {
        $lines[$index] = $replacement
    } else {
        $lines += $replacement
    }
}

Set-Content -LiteralPath $EnvPath -Value $lines -Encoding UTF8
Write-Host "Local secrets configured in .env. This file is ignored by Git."
