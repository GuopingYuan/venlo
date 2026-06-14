@echo off
chcp 65001 >nul
title Venlo Sports Platform Server

REM Switch to backend directory
cd /d "%~dp0venlo\backend"

echo ==================================================
echo   Venlo Sports Platform - Cloud Server Launcher
echo ==================================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed!
    echo Please run setup_cloud.bat first.
    echo.
    pause
    exit /b 1
)

echo [OK] Python found:
python --version
echo.

REM Install dependencies
echo [1/3] Installing dependencies...
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies!
    pip install -r requirements.txt
    pause
    exit /b 1
)
echo [OK] Dependencies installed
echo.

REM Initialize database
echo [2/3] Initializing database...
python -c "from app import init_db; init_db(); print('[OK] Database ready')"
echo.

REM Start server (port 80)
echo [3/3] Starting Venlo server on port 80...
echo.
echo ==================================================
echo   Venlo is running!
echo.
echo   Local:  http://localhost
echo   Cloud:  http://101.42.136.186
echo   API:    http://101.42.136.186/api/ping
echo.
echo   Press Ctrl+C to stop the server
echo ==================================================
echo.

set PORT=80
set FLASK_ENV=production
python app.py
