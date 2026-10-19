@echo off
rem Bot Telegram trả báo cáo ads theo lệnh trong nhóm. Lịch \LAMME\BotBaoCaoAds gọi qua chay_an.vbs (không hiện cửa sổ).
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
rem Python: config\python.txt (tools\dang_ky_lich.ps1) or python in PATH
set "PY=python"
if exist config\python.txt set /p PY=<config\python.txt
"%PY%" -u src\bot_bao_cao_telegram.py >> data\bot_bao_cao.log 2>&1
