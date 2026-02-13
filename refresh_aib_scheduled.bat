@echo off
REM AIB Dashboard - Daily 5AM BigQuery Refresh
REM Runs automatically via Windows Task Scheduler at 5:00 AM

echo ============================================================
echo AIB Dashboard - Daily 5AM BigQuery Refresh
echo Started: %date% %time%
echo ============================================================

REM Set Python path (use the code-puppy venv)
set PYTHON_PATH=C:\Users\o0o01hq\.code-puppy-venv\Scripts\python.exe

REM Set working directory
cd /d "C:\Users\o0o01hq\OneDrive - Walmart Inc\Desktop\Codepuppy"

REM Run the BQ refresh script directly
"%PYTHON_PATH%" refresh_aib_dashboard.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] AIB Dashboard refreshed from BigQuery!
) else (
    echo.
    echo [ERROR] Failed to refresh AIB dashboard. Error code: %ERRORLEVEL%
)

echo ============================================================
echo Completed: %date% %time%
echo Next refresh tomorrow at 5:00 AM
echo ============================================================
