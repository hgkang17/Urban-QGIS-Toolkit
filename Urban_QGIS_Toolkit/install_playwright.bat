@echo off
chcp 65001 >nul
title Playwright Environment Setup
echo ===================================================
echo  Playwright 및 필수 패키지 설치를 시작합니다.
echo ===================================================
echo.

echo [1/4] pip 업그레이드 중...
python -m pip install --upgrade pip
if %errorlevel% neq 0 goto error

echo.
echo [2/4] greenlet 바이너리 설치 중...
python -m pip install --only-binary :all: greenlet
if %errorlevel% neq 0 goto error

echo.
echo [3/4] playwright 설치 중...
python -m pip install playwright
if %errorlevel% neq 0 goto error

echo.
echo [4/4] 크로미움 브라우저 다운로드 중...
python -m playwright install chromium
if %errorlevel% neq 0 goto error

echo.
echo ===================================================
echo  모든 설치가 성공적으로 완료되었습니다!
echo ===================================================
pause
exit

:error
echo.
echo ---------------------------------------------------
echo  [오류] 설치 중 문제가 발생했습니다. 위 메시지를 확인하세요.
echo ---------------------------------------------------