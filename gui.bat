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

echo Uruchamiam miriCAN Studio (GUI) - przegladarka otworzy sie automatycznie...
echo (serwer zamknie sie sam ok. 30 s po zamknieciu przegladarki - zwalnia port COM)
py -m canstudio gui
if errorlevel 1 pause
