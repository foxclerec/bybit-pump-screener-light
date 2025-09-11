@echo off
cd /d "%~dp0"
:: Kill leftover screener processes
for /f "tokens=2 delims=," %%p in ('wmic process where "commandline like '%%screener-run%%' and name='python.exe'" get ProcessId /format:csv 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /F /PID %%p >nul 2>&1
)
call .venv\Scripts\activate.bat
flask --app app:create_app screener-run
pause
