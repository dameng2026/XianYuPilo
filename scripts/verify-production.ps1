[CmdletBinding()]
param(
    [string]$EnvFile,
    [switch]$NoBuild,
    [ValidateRange(30, 1800)]
    [int]$WaitTimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $EnvFile) {
    $EnvFile = Join-Path $Root '.env'
}
$EnvFile = [System.IO.Path]::GetFullPath($EnvFile)

$python = Get-Command python -ErrorAction SilentlyContinue
$pythonPrefix = @()
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
    $pythonPrefix = @('-3')
}
if (-not $python) {
    throw 'Python 3 is required for the secret-safe production verifier.'
}

$arguments = @(
    'scripts/verify_production.py',
    '--env-file', $EnvFile,
    '--wait-timeout', [string]$WaitTimeoutSeconds
)
if ($NoBuild) {
    $arguments += '--no-build'
}

Push-Location $Root
try {
    & $python.Source @pythonPrefix @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Production verification failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}
