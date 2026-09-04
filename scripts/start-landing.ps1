$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot 'frontend'

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

Write-Host 'Starting Transit landing page. The browser will open automatically.' -ForegroundColor Green
Write-Host 'Press Ctrl+C in this window to stop the server.' -ForegroundColor DarkGray
npm run dev -- --host 127.0.0.1 --open
