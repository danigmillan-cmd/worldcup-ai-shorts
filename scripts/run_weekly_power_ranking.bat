@echo off
REM ===========================================================================
REM Entry point for Windows Task Scheduler (weekly Power Ranking Short).
REM
REM Runs `python main.py --type power_ranking` (fresh Elo + Monte Carlo
REM tournament odds, public upload) and appends all output to
REM logs\weekly_power_ranking.log, then exits with the same exit code.
REM
REM Task Scheduler setup:
REM   Program/script : C:\...\worldcup-ai-shorts\scripts\run_weekly_power_ranking.bat
REM   Start in       : C:\...\worldcup-ai-shorts
REM   Trigger        : Weekly, every Sunday 20:00
REM
REM   schtasks /create /tn WorldCupAIShorts_WeeklyPowerRanking ^
REM            /tr "<path>\run_weekly_power_ranking.bat" ^
REM            /sc weekly /d SUN /st 20:00 /f
REM ===========================================================================
setlocal
cd /d "%~dp0\.."

if not exist logs mkdir logs

echo. >> logs\weekly_power_ranking.log
echo ===== %date% %time% ===== >> logs\weekly_power_ranking.log
python main.py --type power_ranking >> logs\weekly_power_ranking.log 2>&1

exit /b %ERRORLEVEL%
