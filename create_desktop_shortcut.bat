@echo off
REM ============================================================
REM  바탕화면에 "KTX 취소표 도우미" 실행 아이콘 만들기
REM  이 파일을 더블클릭하면 바탕화면에 바로가기가 생깁니다.
REM ============================================================
chcp 65001 > nul
setlocal
cd /d "%~dp0"

set "TARGET=%~dp0run_ktx.bat"
set "ICON=%~dp0ktx.ico"
set "WORKDIR=%~dp0"

if not exist "%TARGET%" (
  echo [오류] run_ktx.bat 을 찾을 수 없습니다. 이 파일이 압축 푼 폴더 안에 있는지 확인하세요.
  pause & exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; $lnk=Join-Path $d 'KTX 취소표 도우미.lnk'; $s=$w.CreateShortcut($lnk); $s.TargetPath=$env:TARGET; $s.WorkingDirectory=$env:WORKDIR; if(Test-Path $env:ICON){$s.IconLocation=$env:ICON}; $s.Description='KTX 취소표 예약대기 도우미'; $s.Save(); Write-Host ('바탕화면에 아이콘을 만들었습니다: ' + $lnk)"

if errorlevel 1 (
  echo [오류] 아이콘 생성에 실패했습니다.
) else (
  echo.
  echo 완료! 바탕화면의 "KTX 취소표 도우미" 아이콘을 더블클릭하면 실행됩니다.
)
echo.
pause
endlocal
