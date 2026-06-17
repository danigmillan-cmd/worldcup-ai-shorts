@echo off
REM ===========================================================================
REM Entry point for Windows Task Scheduler (weekly analytics report).
REM
REM Runs `python main.py weekly_report` and appends all output to
REM logs\weekly_report.log, then exits with the same exit code.
REM
REM Task Scheduler setup:
REM   Program/script : C:\...\worldcup-ai-shorts\scripts\run_weekly_report.bat
REM   Start in       : C:\...\worldcup-ai-shorts
REM   Trigger        : Weekly, e.g. every Monday 09:00
REM
REM   schtasks /create /tn WorldCupAIShorts_WeeklyReport ^
REM            /tr "<path>\run_weekly_report.bat" ^
REM            /sc weekly /d MON /st 09:00 /f
REM ===========================================================================
setlocal
cd /d "%~dp0\.."

if not exist logs mkdir logs

echo. >> logs\weekly_report.log
echo ===== %date% %time% ===== >> logs\weekly_report.log
python main.py weekly_report >> logs\weekly_report.log 2>&1

exit /b %ERRORLEVEL%
