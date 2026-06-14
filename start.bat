@echo off
chcp 65001 >nul 2>&1
title Venlo Sports Platform - Backend Server

echo ========================================
echo   Venlo Sports Platform
echo   Starting Backend Server...
echo ========================================
echo.

cd /d "%~dp0"

set PYTHON=C:\Users\lenovo\.workbuddy\binaries\python\envs\venlo\Scripts\python.exe

echo [1/3] Checking Python...
if not exist "%PYTHON%" (
    echo ERROR: Python venv not found at %PYTHON%
    echo Please check the installation.
    pause
    exit /b 1
)
echo        Python found: %PYTHON%

echo [2/3] Installing dependencies...
"%PYTHON%" -m pip install flask flask-cors -q 2>nul
echo        Done.

echo [3/3] Starting server...
echo.
echo ========================================
echo   Server:  http://localhost:5000
echo   Frontend: http://localhost:5000/index.html
echo   API Ping: http://localhost:5000/api/ping
echo ========================================
echo.
echo   Demo Accounts:
echo     Student:  student1 / student123
echo     Teacher:  teacher1 / teacher123
echo     Parent:   parent1  / parent123
echo ========================================
echo.

echo Press Ctrl+C to stop the server.
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5000/index.html"

cd backend
"%PYTHON%" app.py
pause
