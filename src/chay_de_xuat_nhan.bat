@echo off
rem Đề xuất nhân nhóm quảng cáo gửi Telegram. Lịch \LAMME\DeXuatNhan_<giờ>h gọi qua chay_an.vbs (không hiện cửa sổ).
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
rem Python: config\python.txt (tools\dang_ky_lich.ps1) or python in PATH
set "PY=python"
if exist config\python.txt set /p PY=<config\python.txt
echo [%date% %time%] de xuat nhan nhom >> data\de_xuat_nhan.log
"%PY%" src\de_xuat_nhan_nhom.py >> data\de_xuat_nhan.log 2>&1
echo [%date% %time%] xong, ma thoat %errorlevel% >> data\de_xuat_nhan.log
