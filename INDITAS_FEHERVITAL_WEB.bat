@echo off
setlocal
title Fehervital Web - Helyi Admin
cd /d "%~dp0"

echo.
echo =====================================================
echo   FEHERVITAL WEB - HELYI ADMIN ES ELOZETES
 echo =====================================================
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

echo Helyi szerver inditasa...
start "Fehervital Web - Local Admin Server" cmd /k "%PY% local_admin_server.py"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8000/admin/"
start "" "http://127.0.0.1:8000/"

echo.
echo Admin:    http://127.0.0.1:8000/admin/
echo Weboldal: http://127.0.0.1:8000/
echo.
echo A szerver leallitasahoz zard be a szerverablakot,
echo vagy nyomj benne Ctrl+C-t.
exit /b 0
