@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo [!] Nie znaleziono "py" ^(Python Launcher^).
  echo     Zainstaluj Python 3.11+ z python.org i uruchom ponownie.
  echo.
  pause
  exit /b 1
)

py start_menu.py
if errorlevel 1 pause
