@echo off
title QuickServe Legal Server
echo.
echo ========================================
echo    Starting QuickServe Legal...
echo ========================================
echo.

cd /d "C:\Users\Anphia\OneDrive - VEDlaw\Claude_Projekte\QuickServeLegal"
call venv\Scripts\activate

echo.
echo Server starting at: http://localhost:8000
echo Press Ctrl+C to stop the server
echo.

start http://localhost:8000
python -m uvicorn src.main:app --reload --port 8000
