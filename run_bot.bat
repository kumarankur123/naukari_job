@echo off
chcp 65001 >nul
title Naukri Auto Apply Bot
echo ========================================================
echo Starting Naukri Auto Apply Bot...
echo ========================================================
cd /d "%~dp0"
call .\.venv\Scripts\activate.bat
python job_bot.py
pause
