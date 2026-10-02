@echo off
title ChaiGaram Local Launcher
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)
python scripts\start_local.py %*
set "LAUNCH_EXIT=%ERRORLEVEL%"
if not "%LAUNCH_EXIT%"=="0" pause
exit /b %LAUNCH_EXIT%
