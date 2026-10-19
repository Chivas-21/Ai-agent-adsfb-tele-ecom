# Đăng ký các lịch Windows chạy AI AGENT cho 1 doanh nghiệp (chạy 1 lần sau khi cài, trên máy sẽ chạy bot).
#   powershell -ExecutionPolicy Bypass -File tools\dang_ky_lich.ps1            # đăng ký / cập nhật
#   powershell -ExecutionPolicy Bypass -File tools\dang_ky_lich.ps1 -Xoa       # gỡ toàn bộ lịch của DN này
# Thư mục lịch = ten_ngan trong config\doanh_nghiep.yaml (vd \lamme\). Ghi đường dẫn Python vào config\python.txt
# để các file src\chay_*.bat dùng. Các lịch gọi qua src\chay_an.vbs nên không bật cửa sổ.
param([switch]$Xoa)

$ErrorActionPreference = "Stop"
$goc = Split-Path -Parent $PSScriptRoot
$cauHinh = Join-Path $goc "config\doanh_nghiep.yaml"
if (-not (Test-Path $cauHinh)) { throw "Thiếu config\doanh_nghiep.yaml — chép từ config\doanh_nghiep.mau.yaml rồi điền." }
$tenNgan = (Select-String -Path $cauHinh -Pattern '^ten_ngan:\s*([A-Za-z0-9_-]+)').Matches[0].Groups[1].Value
if (-not $tenNgan) { $tenNgan = "agent" }
$thuMuc = "\$tenNgan\"

if ($Xoa) {
    Get-ScheduledTask -TaskPath $thuMuc -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false
    Write-Output "Đã gỡ các lịch trong $thuMuc"
    return
}

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw "Không thấy python trong PATH — cài Python 3.11+ (tick 'Add to PATH')." }
Set-Content -Path (Join-Path $goc "config\python.txt") -Value $py -NoNewline -Encoding ascii

$vbs = Join-Path $goc "src\chay_an.vbs"
function Lich($ten, $bat, $thamSo, $trigger) {
    $doiSo = "`"$vbs`" `"$(Join-Path $goc "src\$bat")`" $thamSo".Trim()
    $act = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $doiSo -WorkingDirectory $goc
    $set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    Register-ScheduledTask -TaskPath $thuMuc -TaskName $ten -Action $act -Trigger $trigger -Settings $set -Force | Out-Null
    Write-Output "  $thuMuc$ten"
}
function Luc($gio, $phut = 0) { New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours($gio).AddMinutes($phut)) }

Write-Output "Đăng ký lịch vào $thuMuc (Python: $py)"
# Bot Telegram nhận lệnh — chạy khi đăng nhập máy, tự giữ 1 bản
Lich "BotBaoCaoAds" "chay_bot_bao_cao.bat" "" (New-ScheduledTaskTrigger -AtLogOn)
# Báo cáo ads + doanh thu lên nhóm Telegram
Lich "BaoCaoAds_08h" "chay_bao_cao_ads.bat" "hom-qua" (Luc 8)          # 8h: tổng kết hôm qua
foreach ($g in 10, 12, 15, 17, 21, 23) { Lich ("BaoCaoAds_{0:D2}h" -f $g) "chay_bao_cao_ads.bat" "hom-nay" (Luc $g) }
# Ngân sách hôm nay 7h, hội thoại Pancake 7h40, cảnh báo nhóm mới 3 tiếng/lần, đề xuất nhân nhóm
Lich "NganSach_07h" "chay_ngan_sach_07h.bat" "" (Luc 7)
Lich "TinNhanPancake" "chay_tin_nhan_pancake.bat" "" (Luc 7 40)
foreach ($g in 8, 11, 14, 17, 20) { Lich ("CanhBaoNhomMoi_{0:D2}h" -f $g) "chay_canh_bao_nhom_moi.bat" "" (Luc $g) }
foreach ($g in 10, 12, 14, 16, 17) { Lich ("DeXuatNhan_{0:D2}h" -f $g) "chay_de_xuat_nhan.bat" "" (Luc $g 5) }
Write-Output "Xong. Đăng ký menu lệnh bot: python src\bot_bao_cao_telegram.py --dang-ky"
