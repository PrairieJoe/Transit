@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-landing.ps1"
if errorlevel 1 (
  echo.
  echo Landing page could not be started. See the message above.
  pause
)
