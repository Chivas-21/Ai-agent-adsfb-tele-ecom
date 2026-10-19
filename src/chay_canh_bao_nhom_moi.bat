@echo off
rem Canh bao nhom QC moi tieu >= 40k ma 0 tin nhan, gui Telegram. Lich \LAMME\CanhBaoNhomMoi (8h-20h, 3 tieng/lan) goi qua chay_an.vbs.
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
rem Python: config\python.txt (tools\dang_ky_lich.ps1) or python in PATH
set "PY=python"
if exist config\python.txt set /p PY=<config\python.txt
"%PY%" src\canh_bao_nhom_moi.py >> data\canh_bao_nhom_moi.log 2>&1
