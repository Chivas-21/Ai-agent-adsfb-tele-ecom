@echo off
rem Ngan sach ads da setup cho hom nay, gui Telegram. Lich \LAMME\NganSach_07h goi qua chay_an.vbs.
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
rem Python: config\python.txt (tools\dang_ky_lich.ps1) or python in PATH
set "PY=python"
if exist config\python.txt set /p PY=<config\python.txt
"%PY%" src\ngan_sach_hom_nay.py >> data\ngan_sach_hom_nay.log 2>&1
echo [%date% %time%] xong, ma thoat %errorlevel% >> data\ngan_sach_hom_nay.log
