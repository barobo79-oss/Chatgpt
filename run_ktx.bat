@echo off
REM ============================================================
REM  KTX 취소표 예약대기 도우미 (합법 버전) - Windows 실행기
REM ============================================================
chcp 65001 > nul
setlocal

cd /d "%~dp0"

REM 파이썬 확인
where python >nul 2>nul
if errorlevel 1 (
  echo [오류] 파이썬이 설치되어 있지 않습니다.
  echo        https://www.python.org 에서 Python 3.10 이상을 설치한 뒤 다시 실행하세요.
  echo        설치 시 "Add Python to PATH" 를 반드시 체크하세요.
  pause
  exit /b 1
)

REM 설정 파일이 없으면 예시를 복사하고 곧바로 웹 설정 화면을 엽니다
if not exist "ktx_config.json" (
  echo [안내] 처음 실행이라 설정 화면을 엽니다. 브라우저에서 여정을 입력하고 저장하세요.
  copy /y "ktx_config.example.json" "ktx_config.json" >nul
  python -m ktx_helper web
  goto end
)

echo.
echo 무엇을 할까요?
echo   [1] 설정 화면 열기(웹)   (web - 여정 편집, 추천)
echo   [2] 여정/알림시각 확인   (plan)
echo   [3] 캘린더로 내보내기    (ics)
echo   [4] 알림 스케줄러 실행   (remind - 창을 켜 두세요)
echo   [5] 알림 테스트          (test)
echo   [6] 전략 요약 보기      (guide)
echo.
set /p choice="번호 입력 (기본 1): "

if "%choice%"=="2" ( python -m ktx_helper plan & goto end )
if "%choice%"=="3" ( python -m ktx_helper ics & goto end )
if "%choice%"=="4" ( python -m ktx_helper remind & goto end )
if "%choice%"=="5" ( python -m ktx_helper test & goto end )
if "%choice%"=="6" ( python -m ktx_helper guide & goto end )
python -m ktx_helper web

:end
echo.
pause
endlocal
