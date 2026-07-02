@echo off
rem ============================================================
rem  Monitor auto-fix launcher
rem  Double-click this file. It finds monitor_fix.ps1 in the
rem  SAME folder automatically - no path typing needed.
rem  (An admin permission popup [UAC] will appear - click Yes)
rem ============================================================
cd /d "%~dp0"
if not exist "%~dp0monitor_fix.ps1" (
  echo [ERROR] monitor_fix.ps1 not found in: %~dp0
  echo Keep run_fix.bat and monitor_fix.ps1 in the same folder.
  pause
  exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0monitor_fix.ps1"
echo.
pause
