@echo off
echo ========================================
echo MFScope - Rebuild Features and Start
echo ========================================
echo.

echo [1/3] Rebuilding features with validation (this takes ~15 minutes)...
echo.
python build_features_and_score.py
if errorlevel 1 (
    echo ERROR: Feature rebuild failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo [2/3] Starting Backend Server...
echo ========================================
echo.
start "MFScope Backend" cmd /k "python -m uvicorn backend.api.main:app --reload"

timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo [3/3] Starting Frontend...
echo ========================================
echo.
start "MFScope Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ========================================
echo All Done! Your servers are starting...
echo ========================================
echo.
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo.
echo Close this window when done.
pause
