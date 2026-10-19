@echo off
rem Tinh truoc hoi thoai tu QC theo nhan vien (Pancake) cho hom qua + ngay con thieu. Lich \LAMME\TinNhanPancake goi qua chay_an.vbs.
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
rem Python: config\python.txt (tools\dang_ky_lich.ps1) or python in PATH
set "PY=python"
if exist config\python.txt set /p PY=<config\python.txt
"%PY%" src\pancake_tin_nhan.py --bu >> data\pancake_tin_nhan.log 2>&1
echo [%date% %time%] xong, ma thoat %errorlevel% >> data\pancake_tin_nhan.log
