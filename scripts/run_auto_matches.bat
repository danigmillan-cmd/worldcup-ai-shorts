@echo off
REM ===========================================================================
REM Entry point for Windows Task Scheduler.
REM
REM Runs `python main.py auto_matches` and appends all output to
REM logs\auto_matches.log, then exits with the same exit code.
REM
REM Task Scheduler setup:
REM   Program/script : C:\...\worldcup-ai-shorts\scripts\run_auto_matches.bat
REM   Start in       : C:\...\worldcup-ai-shorts
REM   Trigger        : Daily, repeat task every 1 hour, for a duration of 1 day
REM   General tab    : "Run whether user is logged on or not"
REM ===========================================================================
setlocal
cd /d "%~dp0\.."

if not exist logs mkdir logs

echo. >> logs\auto_matches.log
echo ===== %date% %time% ===== >> logs\auto_matches.log
python main.py auto_matches >> logs\auto_matches.log 2>&1

exit /b %ERRORLEVEL%
