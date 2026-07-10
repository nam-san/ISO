@echo off
title Nurivoice IMS Server
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cls
echo ==========================================================
echo   Nurivoice ISO IMS - Development Server
echo ==========================================================
echo.

rem First-time setup only if the virtual environment is missing
if not exist ".venv\Scripts\python.exe" call :setup
if not exist ".venv\Scripts\python.exe" goto novenv

rem Ensure data folders exist
if not exist instance mkdir instance
if not exist "static\uploads" mkdir "static\uploads"

rem Free port 5000 if a previous server did not close cleanly
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5000" ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo.
echo   Starting server at http://localhost:5000
echo   Admin : admin / nurivoice2024!
echo   Stop  : press Ctrl+C in this window
echo.
".venv\Scripts\python.exe" app.py
echo.
echo [*] Server stopped.
pause
goto end

:setup
echo [*] First run: creating virtual environment and installing packages...
python -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
goto :eof

:novenv
echo [ERROR] Python virtual environment not found.
echo         Install Python 3.10+ from python.org and run this file again.
pause
exit /b 1

:end
