@echo off
TITLE ChaiGaram Platform Setup & Startup
SETLOCAL EnableDelayedExpansion

echo =========================================================================
echo                   ChaiGaram Platform Setup & Launcher                    
echo =========================================================================
echo.

REM Set script directory as current working directory
cd /d "%~dp0"

echo [1/5] Checking prerequisites...
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not found on PATH. Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

where npm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Node.js/npm is not found on PATH. Please install Node.js 18+ and add it to PATH.
    pause
    exit /b 1
)

echo [OK] Python and Node.js detected.
echo.

echo [2/5] Installing Python Backend and ML dependencies...
if exist "backend\requirements.txt" (
    pip install -r backend\requirements.txt
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to install backend dependencies.
        pause
        exit /b 1
    )
)

if exist "ml\requirements.txt" (
    pip install -r ml\requirements.txt
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to install ML dependencies.
        pause
        exit /b 1
    )
)
echo [OK] Python dependencies installed successfully.
echo.

echo [3/5] Installing Frontend Node.js dependencies...
cd frontend
call npm install
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install frontend dependencies.
    cd ..
    pause
    exit /b 1
)
echo [OK] Frontend packages installed successfully.
echo.

echo [4/5] Building Frontend production assets...
call npm run build
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Frontend build completed with warnings/errors. Proceeding to server launch...
) else (
    echo [OK] Frontend build completed successfully.
)
cd ..
echo.

echo [5/5] Launching ChaiGaram Services...
echo - Starting Backend API on http://127.0.0.1:8000 ...
start "ChaiGaram - Backend API (Port 8000)" cmd /k "cd /d "%~dp0" && python -m uvicorn backend.app:app --port 8000 --reload"

echo - Starting Frontend Web App on http://localhost:8080 ...
start "ChaiGaram - Frontend App (Port 8080)" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo =========================================================================
echo ChaiGaram services are running!
echo.
echo   - Frontend App:  http://localhost:8080
echo   - Backend API:   http://127.0.0.1:8000
echo   - API Docs:      http://127.0.0.1:8000/docs
echo =========================================================================
echo.
pause
