param()

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$WebDir = Join-Path $Root 'apps\web'
$ApiDir = Join-Path $Root 'apps\api'
$CrawlerDir = Join-Path $Root 'apps\crawler'

function Require-Command([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required command not found: $Name"
    }
    return $command.Source
}

function Invoke-CheckedCommand(
    [string]$Name,
    [string]$CommandPath,
    [string[]]$Arguments,
    [string]$WorkingDirectory
) {
    Write-Host "==> $Name"
    $process = Start-Process -FilePath $CommandPath `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -NoNewWindow `
        -Wait `
        -PassThru
    if ($process.ExitCode -ne 0) {
        throw "$Name failed with exit code $($process.ExitCode)."
    }
}

$npm = Require-Command 'npm.cmd'
$python = Require-Command 'python'

Invoke-CheckedCommand -Name 'Web production build' -CommandPath $npm -Arguments @('run', 'build') -WorkingDirectory $WebDir
Invoke-CheckedCommand -Name 'API compile check' -CommandPath $python -Arguments @('-m', 'compileall', '-q', 'app') -WorkingDirectory $ApiDir
Invoke-CheckedCommand -Name 'Crawler build' -CommandPath $npm -Arguments @('run', 'build') -WorkingDirectory $CrawlerDir

Write-Host 'verify-local passed.'
