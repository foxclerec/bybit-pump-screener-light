@echo off
cd /d "%~dp0"
:: Kill leftover Flask web processes on port 5000
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
)
call .venv\Scripts\activate.bat
flask --app app:create_app run --reload --with-threads
pause
