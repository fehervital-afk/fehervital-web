@echo off
setlocal
title Fehervital Web - Helyi ellenorzes

cd /d "%~dp0"

echo.
echo ==============================================
echo   FEHERVITAL WEB - HELYI ELLENORZES
echo ==============================================
echo.

set "PY="

where py >nul 2>&1
if %errorlevel%==0 set "PY=py"

if not defined PY (
    where python >nul 2>&1
    if %errorlevel%==0 set "PY=python"
)

if not defined PY (
    echo HIBA: A Python nem talalhato ezen a gepen.
    echo Telepitsd a Pythont, majd inditsd ujra ezt a fajlt.
    echo.
    pause
    exit /b 1
)

echo Helyi webszerver inditasa: http://localhost:8000
echo A szerver egy kulon ablakban fog futni.
echo.

start "Fehervital Web - Local Server" cmd /k "%PY% -m http.server 8000"

timeout /t 2 /nobreak >nul
start "" "http://localhost:8000"

echo A bongeszo megnyilt.
echo A szerver leallitasahoz zard be a kulon szerverablakot,
echo vagy nyomj benne Ctrl+C-t.
echo.
exit /b 0
