---
name: cai-dat-agent
description: Cài AI AGENT cho một doanh nghiệp mới — tạo config/doanh_nghiep.yaml, doi_tuong.yaml, .env từ mẫu, đọc page + tài khoản QC từ Meta, kiểm tra token Meta/Nhanh/Telegram, đăng trang "Yêu cầu lên camp FB", đăng ký lịch Windows. Dùng khi người dùng nói "cài agent", "thêm doanh nghiệp mới", "thiết lập cho shop X".
---

# Cài AI AGENT cho doanh nghiệp mới

Hướng dẫn chi tiết cho người: `docs/cai_dat.md`. Làm lần lượt, mỗi bước xong mới sang bước sau.

## Quy tắc
- Khoá / token chỉ nằm trong `config/.env`, người dùng **tự dán**; không đọc to, không ghi vào file khác, không gửi đi.
- Không tạo app, tài khoản, khoá thay người dùng; không đổi cài đặt app Meta (bật Live là việc của chủ app).
- Bước đọc Meta / Nhanh chỉ đọc. Không tạo chiến dịch thử.

## Các bước
1. **Cài thư viện**: `python -m pip install -r requirements.txt` (Python 3.11+).
2. **Tạo cấu hình từ mẫu** (nếu chưa có): chép `config/doanh_nghiep.mau.yaml` → `config/doanh_nghiep.yaml`,
   `config/doi_tuong.mau.yaml` → `config/doi_tuong.yaml`, `config/.env.mau` → `config/.env`. Hỏi người dùng tên DN,
   `ten_ngan` (chữ thường không dấu), hậu tố tên chiến dịch, danh mục sản phẩm, nhân viên bán hàng (tên trên Nhanh).
3. **Người dùng dán token** vào `config/.env` (Meta, Nhanh, Telegram, Pancake). Chỉ hướng dẫn chỗ lấy (docs/cai_dat.md).
4. **Đọc Meta**: `python src/khoi_tao.py --meta` → hỏi người dùng page/tài khoản nào dùng rồi điền `meta.pages`,
   `meta.tai_khoan`, `tai_khoan_mac_dinh`, `tai_khoan_quet_bai`. `python src/khoi_tao.py --nhanh` → `nhanh.kenh_san`, `nhanh.kho`.
5. **Kiểm tra**: `python src/khoi_tao.py --kiem-tra` phải báo đủ quyền Meta, Telegram @bot, Nhanh dùng được.
6. **Đối tượng**: `python src/fb_tep_da_luu.py` (lấy đối tượng đã lưu trên Meta); thêm đối tượng tay vào
   `config/doi_tuong.yaml` nếu cần (`python src/fb_ads_create.py --ds-doi-tuong` để xem).
7. **Trang yêu cầu lên camp**: `python html/fb-ads-yeu-cau/build.py` (vài phút) → đăng file
   `html/fb-ads-yeu-cau/fb-ads-yeu-cau.html` thành artifact (capability db với collection `yeu_cau`, comments, user) →
   ghi link vào `trang_yeu_cau`. Nhắc người dùng chia sẻ trang (quyền Editor) cho người gửi yêu cầu.
8. **Lịch Windows** (báo cáo Telegram, bot): `powershell -ExecutionPolicy Bypass -File tools\dang_ky_lich.ps1`, rồi
   `python src/bot_bao_cao_telegram.py --dang-ky`.
9. **Lịch trong phiên Claude**: chạy lệnh `/ai-agent:bat-lich` (hàng đợi lên camp 5 phút/lần, số sàn 60 phút/lần).
10. **Meta app Live** (để chạy QC từ bài nhiều ảnh): chỉ người dùng làm được — mở developers.facebook.com → app →
    Đăng (Publish): điền URL chính sách quyền riêng tư + URL xoá dữ liệu, xác minh doanh nghiệp, rồi bấm Đăng.
