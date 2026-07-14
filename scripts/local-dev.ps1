param(
    [ValidateSet('start', 'stop', 'status', 'preflight')]
    [string]$Action = 'start'
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$OutputDir = Join-Path $Root 'output\local-dev'
$PidDir = Join-Path $OutputDir 'pids'
$ApiDir = Join-Path $Root 'apps\api'
$CrawlerDir = Join-Path $Root 'apps\crawler'
$WebDir = Join-Path $Root 'apps\web'

$ApiPort = 15177
$CrawlerPort = 15178
$WebPort = 15176

$ApiPidFile = Join-Path $PidDir 'api.pid'
$CrawlerPidFile = Join-Path $PidDir 'crawler.pid'
$SchedulerPidFile = Join-Path $PidDir 'scheduler.pid'
$WebPidFile = Join-Path $PidDir 'web.pid'

$ApiStdoutFile = Join-Path $OutputDir 'api.out.log'
$ApiStderrFile = Join-Path $OutputDir 'api.err.log'
$CrawlerStdoutFile = Join-Path $OutputDir 'crawler.out.log'
$CrawlerStderrFile = Join-Path $OutputDir 'crawler.err.log'
$SchedulerStdoutFile = Join-Path $OutputDir 'scheduler.out.log'
$SchedulerStderrFile = Join-Path $OutputDir 'scheduler.err.log'
$SchedulerHeartbeatFile = Join-Path $OutputDir 'scheduler.heartbeat'
$WebStdoutFile = Join-Path $OutputDir 'web.out.log'
$WebStderrFile = Join-Path $OutputDir 'web.err.log'

function Normalize-ProcessPathEnvironment() {
    # Some desktop launchers inject both Path and PATH. Windows treats them as
    # the same variable, but Windows PowerShell Start-Process rejects the
    # duplicate keys. Preserve the canonical Path entry and remove only the
    # duplicate uppercase spelling in this child shell.
    $pathKeys = @(
        [Environment]::GetEnvironmentVariables('Process').Keys |
            Where-Object { $_ -ieq 'Path' }
    )
    if ($pathKeys.Count -gt 1 -and $pathKeys -ccontains 'PATH') {
        [Environment]::SetEnvironmentVariable('PATH', $null, 'Process')
    }
}

function Ensure-Dir([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Test-TcpPort([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(500)) {
            return $false
        }
        $client.EndConnect($async) | Out-Null
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Wait-Port([int]$Port, [int]$TimeoutSeconds, [string]$Name) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort $Port) {
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name did not become ready on port $Port within ${TimeoutSeconds}s."
}

function Wait-HttpReady([string]$Url, [int]$TimeoutSeconds, [string]$Name) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastStatus = 'unreachable'
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            $lastStatus = "HTTP $($response.StatusCode)"
            if ($response.StatusCode -eq 200) {
                return
            }
        } catch {
            if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                $lastStatus = "HTTP $([int]$_.Exception.Response.StatusCode)"
            }
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name did not become ready at $Url within ${TimeoutSeconds}s (last status: $lastStatus)."
}

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
    Push-Location $WorkingDirectory
    try {
        & $CommandPath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Name failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
}

function Read-Pid([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    $raw = (Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $raw) {
        return $null
    }
    $value = 0
    if ([int]::TryParse($raw, [ref]$value)) {
        return $value
    }
    return $null
}

function Get-PortOwningProcessId([int]$Port) {
    try {
        $row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop |
            Select-Object -First 1
        if ($row) {
            return [int]$row.OwningProcess
        }
    } catch {
    }
    # Get-NetTCPConnection can require CIM permissions unavailable in some
    # desktop/sandbox sessions. netstat is read-only and still lets ownership
    # checks fail closed instead of treating an unknown listener as managed.
    $pattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    foreach ($line in @(& netstat -ano 2>$null)) {
        $match = [regex]::Match([string]$line, $pattern)
        if ($match.Success) {
            return [int]$match.Groups[1].Value
        }
    }
    return $null
}

function Assert-LocalPortsAvailable() {
    $services = @(
        @{ Name = 'Web'; Port = $WebPort },
        @{ Name = 'API'; Port = $ApiPort },
        @{ Name = 'Crawler'; Port = $CrawlerPort }
    )
    $conflicts = @()
    foreach ($service in $services) {
        if (Test-TcpPort $service.Port) {
            $ownerPid = Get-PortOwningProcessId $service.Port
            $conflicts += "$($service.Name)=$($service.Port) (PID $ownerPid)"
        }
    }
    if ($conflicts.Count -gt 0) {
        throw "Isolated local port conflict: $($conflicts -join ', '). Stop the conflicting process or choose another complete port set."
    }
    Write-Host "Isolated local ports are available: Web=$WebPort, API=$ApiPort, Crawler=$CrawlerPort."
}

function Get-AliveProcess([string]$PidFile, [int]$Port = 0) {
    $pidValue = Read-Pid $PidFile
    if (-not $pidValue) {
        return $null
    }
    try {
        $process = Get-Process -Id $pidValue -ErrorAction Stop
        if ($Port -gt 0) {
            $ownerPid = Get-PortOwningProcessId $Port
            if (-not $ownerPid -or $ownerPid -ne $pidValue) {
                Remove-PidFile $PidFile
                return $null
            }
        }
        return $process
    } catch {
        Remove-PidFile $PidFile
        return $null
    }
}

function Save-Pid([string]$Path, [int]$PidValue) {
    Set-Content -LiteralPath $Path -Value $PidValue -Encoding ascii
}

function Remove-PidFile([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Force
    }
}

function Start-ServiceProcess(
    [string]$Name,
    [string]$CommandPath,
    [string[]]$Arguments,
    [string]$WorkingDirectory,
    [string]$PidFile,
    [string]$StdoutFile,
    [string]$StderrFile,
    [int]$Port,
    [int]$TimeoutSeconds
) {
    $existing = Get-AliveProcess $PidFile $Port
    if ($existing) {
        Write-Host "$Name already running (PID $($existing.Id))."
        return
    }

    if (Test-TcpPort $Port) {
        $ownerPid = Get-PortOwningProcessId $Port
        throw "$Name port $Port is already in use by unmanaged PID $ownerPid."
    }

    if (Test-Path -LiteralPath $StdoutFile) { Remove-Item -LiteralPath $StdoutFile -Force }
    if (Test-Path -LiteralPath $StderrFile) { Remove-Item -LiteralPath $StderrFile -Force }

    $process = Start-Process `
        -FilePath $CommandPath `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $StdoutFile `
        -RedirectStandardError $StderrFile `
        -WindowStyle Hidden `
        -PassThru

    Save-Pid $PidFile $process.Id
    try {
        Wait-Port -Port $Port -TimeoutSeconds $TimeoutSeconds -Name $Name
        $ownerPid = Get-PortOwningProcessId $Port
        if ($ownerPid -ne $process.Id) {
            throw "$Name port $Port was acquired by unexpected PID $ownerPid instead of managed PID $($process.Id)."
        }
        Write-Host "$Name started on port $Port (PID $($process.Id))."
    } catch {
        try { Stop-ProcessTree $process.Id } catch {}
        Remove-PidFile $PidFile
        throw
    }
}

function Stop-ProcessTree([int]$PidValue) {
    if (-not $PidValue) {
        return
    }
    & taskkill /PID $PidValue /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        try {
            Get-Process -Id $PidValue -ErrorAction Stop | Out-Null
        } catch {
            return
        }
        throw "taskkill failed for still-running PID $PidValue with exit code $LASTEXITCODE."
    }
}

function Stop-ServiceProcess([string]$Name, [string]$PidFile, [int]$Port) {
    $pidValue = Read-Pid $PidFile
    $ownerPid = Get-PortOwningProcessId $Port

    if (-not $pidValue) {
        if ($ownerPid) {
            Write-Warning "$Name port $Port is owned by unmanaged PID $ownerPid; it was preserved."
        } else {
            Write-Host "$Name is not running."
        }
        return
    }

    if (-not $ownerPid -or $ownerPid -ne $pidValue) {
        Remove-PidFile $PidFile
        if ($ownerPid) {
            Write-Warning "$Name PID file did not match port owner $ownerPid; the unmanaged process was preserved."
        } else {
            Write-Host "$Name is not running; removed stale PID file."
        }
        return
    }

    try {
        Stop-ProcessTree $pidValue
        Remove-PidFile $PidFile
        Write-Host "$Name stopped."
    } catch {
        throw "Failed to stop managed $Name PID $pidValue."
    }
}

function Test-ProcessCommandOwnership(
    [int]$PidValue,
    [string]$ExpectedExecutable
) {
    if (-not $PidValue) {
        return $false
    }

    try {
        $record = Get-CimInstance `
            -ClassName Win32_Process `
            -Filter "ProcessId = $PidValue" `
            -ErrorAction Stop |
            Select-Object -First 1
    } catch {
        return $false
    }

    if (-not $record) {
        return $false
    }

    $actualExecutable = [string]$record.ExecutablePath
    $commandLine = [string]$record.CommandLine
    if ([string]::IsNullOrWhiteSpace($actualExecutable) -or [string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }

    # A PID can be reused after a stale PID file is left behind. Require both
    # the Python executable identity and the exact worker module invocation;
    # merely finding a live PID is never enough to claim process ownership.
    $actualExecutableName = [IO.Path]::GetFileName($actualExecutable)
    if ($actualExecutableName -notmatch '^python(?:\d+(?:\.\d+)*)?\.exe$') {
        return $false
    }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedExecutable)) {
        try {
            $actualFullPath = [IO.Path]::GetFullPath($actualExecutable)
            $expectedFullPath = [IO.Path]::GetFullPath($ExpectedExecutable)
        } catch {
            return $false
        }
        if (-not [string]::Equals($actualFullPath, $expectedFullPath, [StringComparison]::OrdinalIgnoreCase)) {
            return $false
        }
    }

    return $commandLine -match '^\s*(?:"[^"]+"|\S+)\s+-m\s+app\.worker\s*$'
}

function Get-SchedulerProcessState([string]$ExpectedExecutable) {
    $pidValue = Read-Pid $SchedulerPidFile
    if (-not $pidValue) {
        if (Test-Path -LiteralPath $SchedulerPidFile) {
            Remove-PidFile $SchedulerPidFile
        }
        return [pscustomobject]@{
            Pid = $null
            Alive = $false
            Owned = $false
        }
    }

    try {
        Get-Process -Id $pidValue -ErrorAction Stop | Out-Null
    } catch {
        Remove-PidFile $SchedulerPidFile
        return [pscustomobject]@{
            Pid = $null
            Alive = $false
            Owned = $false
        }
    }

    return [pscustomobject]@{
        Pid = $pidValue
        Alive = $true
        Owned = [bool](Test-ProcessCommandOwnership -PidValue $pidValue -ExpectedExecutable $ExpectedExecutable)
    }
}

function Test-SchedulerHeartbeat(
    [string]$PythonPath,
    [string]$WorkingDirectory
) {
    if ([string]::IsNullOrWhiteSpace($PythonPath)) {
        return $false
    }

    Push-Location $WorkingDirectory
    try {
        $healthArguments = @('-m', 'app.worker', '--check')
        & $PythonPath @healthArguments *> $null
        $exitCode = $LASTEXITCODE
        return $exitCode -eq 0
    } catch {
        return $false
    } finally {
        Pop-Location
    }
}

function Wait-SchedulerReady(
    [int]$PidValue,
    [string]$ExpectedExecutable,
    [string]$WorkingDirectory,
    [int]$TimeoutSeconds
) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $state = Get-SchedulerProcessState -ExpectedExecutable $ExpectedExecutable
        if (-not $state.Alive -or $state.Pid -ne $PidValue) {
            throw "Scheduler exited before it became healthy."
        }
        if (-not $state.Owned) {
            throw "Scheduler PID $PidValue command ownership could not be verified."
        }
        if (Test-SchedulerHeartbeat -PythonPath $ExpectedExecutable -WorkingDirectory $WorkingDirectory) {
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Scheduler did not publish a healthy heartbeat within ${TimeoutSeconds}s."
}

function Start-SchedulerProcess(
    [string]$PythonPath,
    [string]$WorkingDirectory,
    [int]$TimeoutSeconds
) {
    $existing = Get-SchedulerProcessState -ExpectedExecutable $PythonPath
    if ($existing.Alive) {
        if (-not $existing.Owned) {
            throw "Scheduler PID file points to live PID $($existing.Pid), but its command ownership could not be verified. The process was preserved."
        }
        Wait-SchedulerReady -PidValue $existing.Pid -ExpectedExecutable $PythonPath -WorkingDirectory $WorkingDirectory -TimeoutSeconds $TimeoutSeconds
        Write-Host "Scheduler already running and healthy (PID $($existing.Pid))."
        return
    }

    foreach ($path in @($SchedulerStdoutFile, $SchedulerStderrFile, $SchedulerHeartbeatFile)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }

    $process = $null
    try {
        $process = Start-Process `
            -FilePath $PythonPath `
            -ArgumentList @('-m', 'app.worker') `
            -WorkingDirectory $WorkingDirectory `
            -RedirectStandardOutput $SchedulerStdoutFile `
            -RedirectStandardError $SchedulerStderrFile `
            -WindowStyle Hidden `
            -PassThru

        Save-Pid $SchedulerPidFile $process.Id
        Wait-SchedulerReady -PidValue $process.Id -ExpectedExecutable $PythonPath -WorkingDirectory $WorkingDirectory -TimeoutSeconds $TimeoutSeconds
        Write-Host "Scheduler started and healthy (PID $($process.Id))."
    } catch {
        $startupError = $_
        $preserveManagedState = $false
        if ($process) {
            $startedProcessAlive = $false
            try {
                Get-Process -Id $process.Id -ErrorAction Stop | Out-Null
                $startedProcessAlive = $true
            } catch {
            }

            if ($startedProcessAlive) {
                $startedProcessOwned = Test-ProcessCommandOwnership -PidValue $process.Id -ExpectedExecutable $PythonPath
                if ($startedProcessOwned) {
                    try {
                        Stop-ProcessTree $process.Id
                    } catch {
                        $preserveManagedState = $true
                        Write-Warning $_.Exception.Message
                    }
                } else {
                    $preserveManagedState = $true
                    Write-Warning "Scheduler startup PID $($process.Id) could not be proven owned; it and any PID file were preserved."
                }
            }
        }

        if (-not $preserveManagedState) {
            $savedPid = Read-Pid $SchedulerPidFile
            if (-not $process -or -not $savedPid -or $savedPid -eq $process.Id) {
                Remove-PidFile $SchedulerPidFile
            }
            Remove-Item -LiteralPath $SchedulerHeartbeatFile -Force -ErrorAction SilentlyContinue
        }
        throw $startupError
    }
}

function Stop-SchedulerProcess([string]$ExpectedExecutable) {
    $state = Get-SchedulerProcessState -ExpectedExecutable $ExpectedExecutable
    if (-not $state.Alive) {
        Remove-Item -LiteralPath $SchedulerHeartbeatFile -Force -ErrorAction SilentlyContinue
        Write-Host "Scheduler is not running."
        return
    }
    if (-not $state.Owned) {
        throw "Scheduler PID $($state.Pid) command ownership could not be verified. The process and PID file were preserved."
    }

    $pidValue = $state.Pid
    try {
        Stop-ProcessTree $pidValue
        Remove-PidFile $SchedulerPidFile
        Remove-Item -LiteralPath $SchedulerHeartbeatFile -Force -ErrorAction SilentlyContinue
        Write-Host "Scheduler stopped."
    } catch {
        throw "Failed to stop managed Scheduler PID $pidValue."
    }
}

function Show-Status() {
    $rows = @(
        @{ Name = 'API'; PidFile = $ApiPidFile; Port = $ApiPort; Url = "http://127.0.0.1:$ApiPort/health" },
        @{ Name = 'Crawler'; PidFile = $CrawlerPidFile; Port = $CrawlerPort; Url = "http://127.0.0.1:$CrawlerPort" },
        @{ Name = 'Web'; PidFile = $WebPidFile; Port = $WebPort; Url = "http://127.0.0.1:$WebPort/#/login" }
    )

    foreach ($row in $rows) {
        $process = Get-AliveProcess $row.PidFile $row.Port
        $portOpen = Test-TcpPort $row.Port
        $portOwner = Get-PortOwningProcessId $row.Port
        $pidText = if ($process) { $process.Id } elseif ($portOwner) { $portOwner } else { '-' }
        Write-Host ("{0,-8} pid={1,-6} portOpen={2,-5} url={3}" -f $row.Name, $pidText, $portOpen, $row.Url)
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    $expectedExecutable = if ($pythonCommand) { $pythonCommand.Source } else { $null }
    $scheduler = Get-SchedulerProcessState -ExpectedExecutable $expectedExecutable
    $schedulerHealthy = $false
    if ($scheduler.Alive -and $scheduler.Owned) {
        $schedulerHealthy = Test-SchedulerHeartbeat -PythonPath $expectedExecutable -WorkingDirectory $ApiDir
    }
    $schedulerPid = if ($scheduler.Pid) { $scheduler.Pid } else { '-' }
    Write-Host ("{0,-8} pid={1,-6} owned={2,-5} healthy={3,-5} command={4}" -f 'Scheduler', $schedulerPid, $scheduler.Owned, $schedulerHealthy, 'python -m app.worker')
}

Ensure-Dir $OutputDir
Ensure-Dir $PidDir
Normalize-ProcessPathEnvironment
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:SCHEDULER_HEARTBEAT_PATH = $SchedulerHeartbeatFile

switch ($Action) {
    'start' {
        if (-not (Test-Path -LiteralPath (Join-Path $Root '.env'))) {
            throw '.env is required. Copy .env.development.example and configure it first.'
        }

        # Process-level values intentionally override stale local .env port
        # entries without mutating the user's secret-bearing file.
        $env:SERVER_HOST = '127.0.0.1'
        $env:SERVER_PORT = [string]$ApiPort
        $env:API_RELOAD = 'false'
        $env:CRAWLER_PORT = [string]$CrawlerPort
        $env:PORT = [string]$CrawlerPort
        $env:HOST = '127.0.0.1'
        $env:CRAWLER_BASE_URL = "http://127.0.0.1:$CrawlerPort"
        $env:CRAWLER_SERVICE_URL = "http://127.0.0.1:$CrawlerPort"
        $env:XYA_WEB_PORT = [string]$WebPort
        $env:XYA_WEB_HOST = '127.0.0.1'
        $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
        $env:VITE_UPLOAD_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
        $env:CORS_ALLOWED_ORIGINS = "http://127.0.0.1:$WebPort,http://localhost:$WebPort"
        $env:CRAWLER_ALLOWED_ORIGINS = $env:CORS_ALLOWED_ORIGINS

        Assert-LocalPortsAvailable
        $python = Require-Command 'python'
        $node = Require-Command 'node'
        $npm = Require-Command 'npm.cmd'

        Invoke-CheckedCommand -Name 'Database migrations' -CommandPath $python -Arguments @('-m', 'app.migrations', 'upgrade') -WorkingDirectory $ApiDir
        Invoke-CheckedCommand -Name 'Crawler build' -CommandPath $npm -Arguments @('run', 'build') -WorkingDirectory $CrawlerDir

        try {
            Start-ServiceProcess -Name 'Crawler' -CommandPath $node -Arguments @('--env-file=../../.env', 'dist/server.js') -WorkingDirectory $CrawlerDir -PidFile $CrawlerPidFile -StdoutFile $CrawlerStdoutFile -StderrFile $CrawlerStderrFile -Port $CrawlerPort -TimeoutSeconds 20
            Start-ServiceProcess -Name 'API' -CommandPath $python -Arguments @('run.py') -WorkingDirectory $ApiDir -PidFile $ApiPidFile -StdoutFile $ApiStdoutFile -StderrFile $ApiStderrFile -Port $ApiPort -TimeoutSeconds 30
            Start-SchedulerProcess -PythonPath $python -WorkingDirectory $ApiDir -TimeoutSeconds 30
            Start-ServiceProcess -Name 'Web' -CommandPath $node -Arguments @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', [string]$WebPort, '--strictPort') -WorkingDirectory $WebDir -PidFile $WebPidFile -StdoutFile $WebStdoutFile -StderrFile $WebStderrFile -Port $WebPort -TimeoutSeconds 20

            Wait-HttpReady -Url "http://127.0.0.1:$CrawlerPort/ready" -TimeoutSeconds 30 -Name 'Crawler'
            Wait-HttpReady -Url "http://127.0.0.1:$ApiPort/health/ready" -TimeoutSeconds 60 -Name 'API'
            Wait-HttpReady -Url "http://127.0.0.1:$WebPort/" -TimeoutSeconds 20 -Name 'Web'
            Show-Status
        } catch {
            $startupError = $_
            Write-Warning 'Local stack startup failed; rolling back only managed processes.'
            try { Stop-ServiceProcess -Name 'Web' -PidFile $WebPidFile -Port $WebPort } catch { Write-Warning $_.Exception.Message }
            try { Stop-SchedulerProcess -ExpectedExecutable $python } catch { Write-Warning $_.Exception.Message }
            try { Stop-ServiceProcess -Name 'API' -PidFile $ApiPidFile -Port $ApiPort } catch { Write-Warning $_.Exception.Message }
            try { Stop-ServiceProcess -Name 'Crawler' -PidFile $CrawlerPidFile -Port $CrawlerPort } catch { Write-Warning $_.Exception.Message }
            throw $startupError
        }
    }
    'stop' {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        $expectedExecutable = if ($pythonCommand) { $pythonCommand.Source } else { $null }
        $stopErrors = @()
        try { Stop-SchedulerProcess -ExpectedExecutable $expectedExecutable } catch { $stopErrors += $_.Exception.Message }
        try { Stop-ServiceProcess -Name 'Web' -PidFile $WebPidFile -Port $WebPort } catch { $stopErrors += $_.Exception.Message }
        try { Stop-ServiceProcess -Name 'Crawler' -PidFile $CrawlerPidFile -Port $CrawlerPort } catch { $stopErrors += $_.Exception.Message }
        try { Stop-ServiceProcess -Name 'API' -PidFile $ApiPidFile -Port $ApiPort } catch { $stopErrors += $_.Exception.Message }
        if ($stopErrors.Count -gt 0) {
            throw "Local stack stop completed with errors: $($stopErrors -join '; ')"
        }
    }
    'status' {
        Show-Status
    }
    'preflight' {
        Assert-LocalPortsAvailable
    }
}
