@echo off
chcp 65001 >nul
title Naukri Bot Stats
cd /d "%~dp0"
call .\.venv\Scripts\activate.bat
python check_jobs.py
