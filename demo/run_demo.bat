@echo off
echo ========================================
echo   V2X 6G RIS Mobility Demo Launcher
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

echo [2/3] Installing dependencies...
pip install -r requirements.txt --quiet

echo [3/3] Launching Demo...
echo.
echo ========================================
echo   Demo is running at: http://localhost:8501
echo   Press Ctrl+C to stop
echo ========================================
echo.

python -m streamlit run app.py --server.port 8501 --server.headless true

pause
