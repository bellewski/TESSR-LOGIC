@echo off
echo ========================================
echo   TESSR-LOGIC - Multi-Agent Build System
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

REM Check if uvicorn is available
python -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
    echo Installing backend dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
)

echo Starting TESSR-LOGIC...
echo Open http://localhost:8000 in your browser
echo Press Ctrl+C to stop
echo.

set PYTHONPATH=%~dp0backend\..
if exist .env (
    python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --no-access-log --env-file .env
) else (
    python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --no-access-log
)

if errorlevel 1 (
    echo.
    echo Server stopped with error.
    pause
)
