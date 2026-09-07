[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runDirectory = Join-Path $projectRoot ".run"
$pidFile = Join-Path $runDirectory "server.pid"

if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host "No managed server PID was found. The server may not be running." -ForegroundColor Yellow
    exit 0
}

$savedPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
if ($savedPid -notmatch '^\d+$') {
    Remove-Item -LiteralPath $pidFile -Force
    throw "Invalid PID file was removed. No process was stopped."
}

$managedProcess = Get-Process -Id ([int]$savedPid) -ErrorAction SilentlyContinue
if (-not $managedProcess) {
    Remove-Item -LiteralPath $pidFile -Force
    Write-Host "Server is already stopped. The stale PID file was removed." -ForegroundColor Yellow
    exit 0
}

$expectedPython = (Resolve-Path -LiteralPath $pythonPath).Path
$actualPython = $managedProcess.Path
if (-not $actualPython -or -not $actualPython.Equals($expectedPython, [StringComparison]::OrdinalIgnoreCase)) {
    throw "PID $savedPid does not use this project's virtual environment. Refusing to stop an unrelated process."
}

& taskkill.exe /PID $savedPid /T /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to stop the managed server process tree (PID $savedPid)."
}

Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue

for ($attempt = 0; $attempt -lt 20; $attempt++) {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:8910/api/market/session" -UseBasicParsing -TimeoutSec 1 | Out-Null
        Start-Sleep -Milliseconds 250
    } catch {
        Write-Host "Server stopped (PID $savedPid)." -ForegroundColor Green
        exit 0
    }
}

throw "The managed process tree stopped, but port 8910 is still serving. Another server may be running."
