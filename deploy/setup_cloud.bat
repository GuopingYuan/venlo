@echo off
chcp 65001 >nul
title Venlo Cloud Setup
echo ===================================================
echo   Venlo Cloud Server - First Time Setup
echo ===================================================
echo.

REM Switch to script directory
cd /d "%~dp0"

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Python not found, downloading Python 3.12...
    echo.
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"
    if not exist "%TEMP%\python_installer.exe" (
        echo [ERROR] Failed to download Python!
        echo Please install manually from https://www.python.org/downloads/
        echo IMPORTANT: Check "Add Python to PATH" during installation!
        pause
        exit /b 1
    )
    echo [INFO] Installing Python silently...
    %TEMP%\python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
    del %TEMP%\python_installer.exe >nul 2>&1
    echo [OK] Python installed. Please CLOSE and RE-OPEN this script.
    echo.
    pause
    exit /b 0
)

echo [OK] Python found:
python --version
echo.

REM Install dependencies
echo [1/3] Installing Python dependencies...
pip install flask flask-cors waitress --quiet
echo [OK] Dependencies installed
echo.

REM Configure firewall (open port 80)
echo [2/3] Configuring Windows Firewall (port 80)...
netsh advfirewall firewall add rule name="Venlo HTTP" dir=in action=allow protocol=tcp localport=80 >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Firewall rule added for port 80
) else (
    echo [WARN] Could not add firewall rule automatically.
    echo        Run this script as Administrator, or manually open port 80.
    echo        Also check Tencent Cloud security group: allow inbound TCP 80.
)
echo.

REM Initialize database
echo [3/3] Initializing database...
cd venlo\backend
python -c "from app import init_db; init_db(); print('[OK] Database ready')"
cd ..\..
echo.

echo ===================================================
echo   Setup complete!
echo.
echo   NEXT: Double-click start_cloud.bat to launch.
echo.
echo   REMINDER: Open Tencent Cloud console and add
echo   inbound rule: TCP port 80 in security group!
echo ===================================================
pause
