[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$utf8Encoding = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8Encoding
[Console]::OutputEncoding = $utf8Encoding
$OutputEncoding = $utf8Encoding
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runDirectory = Join-Path $projectRoot ".run"
$pidFile = Join-Path $runDirectory "server.pid"
$stdoutLog = Join-Path $runDirectory "server.log"
$stderrLog = Join-Path $runDirectory "server-error.log"
$port = if ($env:VIBE_PORT) { [int]$env:VIBE_PORT } else { 8910 }

function Test-ServerReady {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/market/session" -UseBasicParsing -TimeoutSec 1
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python virtual environment not found: $pythonPath`nRun: py -3.12 -m venv .venv"
}

New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null

if (Test-Path -LiteralPath $pidFile) {
    $savedPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    if ($savedPid -match '^\d+$') {
        $existing = Get-Process -Id ([int]$savedPid) -ErrorAction SilentlyContinue
        if ($existing) {
            if (Test-ServerReady) {
                Write-Host "Server is already running (PID $savedPid)." -ForegroundColor Yellow
                Write-Host "URL: http://127.0.0.1:$port"
                exit 0
            }
            & taskkill.exe /PID $savedPid /T /F | Out-Null
        }
    }
    Remove-Item -LiteralPath $pidFile -Force
}

$occupied = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($occupied) {
    throw "Port $port is already used by PID $($occupied[0].OwningProcess). Server was not started."
}

$process = Start-Process `
    -FilePath $pythonPath `
    -ArgumentList @("-X", "utf8", "server.py") `
    -WorkingDirectory $projectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ascii

for ($attempt = 0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 250
    $process.Refresh()
    if ($process.HasExited) {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        $details = if (Test-Path -LiteralPath $stderrLog) {
            (Get-Content -LiteralPath $stderrLog -Encoding UTF8 -Tail 20) -join "`n"
        } else {
            "No error log was produced."
        }
        throw "Server failed to start:`n$details"
    }

    if (Test-ServerReady) {
        Write-Host "Server started successfully (PID $($process.Id))." -ForegroundColor Green
        Write-Host "URL: http://127.0.0.1:$port"
        Write-Host "Logs: $runDirectory"
        exit 0
    }
}

Write-Host "Server process started (PID $($process.Id)), but port is not ready yet." -ForegroundColor Yellow
Write-Host "Check log: $stderrLog"
