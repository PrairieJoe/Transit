$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot 'frontend'
$apiScript = Join-Path $PSScriptRoot 'start-api.ps1'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw 'Python 3.11 or newer is required. Install Python and run this file again.'
}

python -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host 'Installing backend dependencies...' -ForegroundColor Cyan
  python -m pip install -e "${projectRoot}[api]"
}

$apiRunning = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
if (-not $apiRunning) {
  Start-Process -FilePath 'powershell.exe' -ArgumentList @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $apiScript
  ) -WorkingDirectory $projectRoot
  Start-Sleep -Seconds 2
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  throw 'Node.js is required. Install Node.js 18 or newer and run this file again.'
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw 'npm is required. Install Node.js (which includes npm) and run this file again.'
}

Set-Location $frontendRoot

if (-not (Test-Path (Join-Path $frontendRoot 'node_modules'))) {
  Write-Host 'Installing frontend dependencies...' -ForegroundColor Cyan
  npm ci
}

Write-Host 'Starting Transit landing page with the API. The browser will open automatically.' -ForegroundColor Green
Write-Host 'Press Ctrl+C in this window to stop the server.' -ForegroundColor DarkGray
npm run dev -- --host 127.0.0.1 --open
