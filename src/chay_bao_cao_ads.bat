@echo off
rem Gửi báo cáo ads lên Telegram. Dùng: chay_bao_cao_ads.bat hom-qua|hom-nay
rem Lịch BaoCaoAds_* gọi qua chay_an.vbs để không bật cửa sổ (đóng cửa sổ = ngắt báo cáo)
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
rem Python: config\python.txt (tools\dang_ky_lich.ps1) or python in PATH
set "PY=python"
if exist config\python.txt set /p PY=<config\python.txt
echo [%date% %time%] --ngay %1 >> data\bao_cao_ads.log
"%PY%" src\bao_cao_ads_telegram.py --ngay %1 >> data\bao_cao_ads.log 2>&1
echo [%date% %time%] xong, ma thoat %errorlevel% >> data\bao_cao_ads.log
