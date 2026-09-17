@echo off
REM Manufacturing Dashboard - Development Startup Script (Windows)
REM This script starts both the backend and frontend servers

echo ======================================================
echo    Manufacturing Dashboard - Development Mode
echo ======================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed. Please install Python 3.7 or higher.
    pause
    exit /b 1
)

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed. Please install Node.js.
    pause
    exit /b 1
)

echo Python found
python --version
echo Node.js found
node --version
echo.

REM Check if FastAPI is installed
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo Installing FastAPI dependencies...
    pip install fastapi uvicorn pydantic
    echo.
)

echo Starting services...
echo.

REM Start the backend in a new window
echo Starting FastAPI backend on http://localhost:8000
start "Manufacturing Dashboard - Backend" cmd /k "python fastapi_backend_example.py"

REM Wait a moment for backend to start
timeout /t 3 /nobreak >nul

REM Start the frontend in a new window
echo Starting React frontend on http://localhost:3000
start "Manufacturing Dashboard - Frontend" cmd /k "npm start"

echo.
echo ======================================================
echo    Services Starting
echo ======================================================
echo Backend API:  http://localhost:8000
echo API Docs:     http://localhost:8000/docs
echo Frontend:     http://localhost:3000
echo.
echo Close the backend and frontend windows to stop services
echo ======================================================
echo.

pause
