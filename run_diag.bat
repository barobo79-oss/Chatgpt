@echo off
rem ============================================================
rem  Monitor diagnostic launcher (read-only)
rem  Double-click this file. It finds monitor_diag.ps1 in the
rem  SAME folder automatically - no path typing needed.
rem ============================================================
cd /d "%~dp0"
if not exist "%~dp0monitor_diag.ps1" (
  echo [ERROR] monitor_diag.ps1 not found in: %~dp0
  echo Keep run_diag.bat and monitor_diag.ps1 in the same folder.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0monitor_diag.ps1"
echo.
pause
