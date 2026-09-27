@echo off
REM ============================================================
REM  KTX 도우미 - Windows 자동 시작 등록/해제
REM  로그인할 때마다 알림 스케줄러(remind)를 백그라운드로 실행합니다.
REM  (PC를 켜 두는 경우용. PC를 끄면 GitHub Actions 방식을 쓰세요.)
REM ============================================================
chcp 65001 > nul
setlocal
cd /d "%~dp0"

set TASKNAME=KTX_취소표_알림

where pythonw >nul 2>nul
if errorlevel 1 (
  echo [오류] 파이썬(pythonw)이 없습니다. python.org 에서 설치하세요.
  pause & exit /b 1
)
for /f "delims=" %%i in ('where pythonw') do set PYW=%%i

echo.
echo   [1] 자동 시작 등록   (로그인 시 백그라운드 실행)
echo   [2] 자동 시작 해제
echo.
set /p sel="번호 입력: "

if "%sel%"=="2" (
  schtasks /delete /tn "%TASKNAME%" /f
  echo 해제했습니다.
  pause & exit /b 0
)

schtasks /create /tn "%TASKNAME%" /sc onlogon /rl highest /f ^
  /tr "\"%PYW%\" -m ktx_helper -c \"%~dp0ktx_config.json\" remind"
if errorlevel 1 (
  echo [오류] 등록 실패. 관리자 권한으로 다시 실행해 보세요.
) else (
  echo 등록 완료. 다음 로그인부터 자동 실행됩니다. 지금 바로 시작하려면:
  echo   schtasks /run /tn "%TASKNAME%"
)
pause
endlocal
