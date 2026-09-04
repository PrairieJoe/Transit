$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot 'src'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw 'Python 3.11 or newer is required. Install Python and run start-landing.cmd again.'
}

Write-Host 'Starting Transit API at http://127.0.0.1:8000' -ForegroundColor Green
Write-Host 'Close this window to stop the API server.' -ForegroundColor DarkGray
python -m uvicorn transit.api.server:app --host 127.0.0.1 --port 8000
