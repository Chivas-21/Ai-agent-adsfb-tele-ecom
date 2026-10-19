# Cài AI AGENT cho một doanh nghiệp

Bộ chạy trên **máy Windows** luôn bật (bot Telegram, báo cáo theo lịch) và **Claude Code / app Claude** (lên camp từ
hàng đợi, lấy số sàn qua Chrome). Mọi thông tin riêng của doanh nghiệp nằm trong 3 file, tạo từ file mẫu:

| File | Chứa | Mẫu |
|---|---|---|
| `config/doanh_nghiep.yaml` | page, tài khoản QC, danh mục, nhân viên, shop sàn, kênh Nhanh… | `config/doanh_nghiep.mau.yaml` |
| `config/doi_tuong.yaml` | đối tượng nhắm mục tiêu khi lên camp | `config/doi_tuong.mau.yaml` |
| `config/.env` | token / khoá (không gửi cho ai) | `config/.env.mau` |
| `config/mau_tin_nhan.json` | tin nhắn chào mặc định của QC Messenger (tuỳ chọn) | `config/mau_tin_nhan.mau.json` |

Cách nhanh nhất: mở thư mục bộ bằng Claude Code, cài plugin `plugin/` (`/plugin marketplace add ./plugin` rồi
`/plugin install ai-agent@ai-agent-kinh-doanh`) và gõ **`/ai-agent:cai-dat`** — Claude làm lần lượt các bước dưới đây.

## 1. Chuẩn bị (chủ doanh nghiệp tự làm)

1. **Python 3.11+** (tick "Add python.exe to PATH"), rồi trong thư mục bộ: `python -m pip install -r requirements.txt`.
2. **Meta**
   - App trên developers.facebook.com (loại Business), gắn vào Business Manager của doanh nghiệp, thêm trường hợp sử
     dụng "Tạo và quản lý quảng cáo bằng API Marketing".
   - Token người dùng dài hạn có quyền `ads_management, ads_read, business_management, pages_show_list,
     pages_read_engagement`: điền `FB_APP_ID`, `FB_APP_SECRET` vào `config/.env` rồi chạy `python src/get_fb_token.py`.
   - **Chuyển app sang Live** (mục "Đăng"/Publish của app): cần URL chính sách quyền riêng tư, URL xoá dữ liệu, xác minh
     doanh nghiệp. Chưa Live thì vẫn lên camp bằng bài video / reel / 1 ảnh được, riêng **bài nhiều ảnh** (Claude dựng
     QC carousel) bị Meta chặn (lỗi 1885183).
3. **Nhanh.vn**: tạo app ở open.nhanh.vn, điền `NHANH_APP_ID`, `NHANH_SECRET_KEY`, `NHANH_BUSINESS_ID`,
   `NHANH_RETURN_LINK` rồi `python src/get_access_token.py` (token hạn 1 năm).
4. **Telegram**: tạo bot với @BotFather → `TELEGRAM_BOT_TOKEN`; thêm bot vào nhóm báo cáo, lấy id nhóm (số âm) →
   `TELEGRAM_CHAT_ID`.
5. **Pancake** (tuỳ chọn, cho /tinnhan, /chotdon): token API công khai của từng page → biến `PANCAKE_TOKEN_…` khớp
   `pancake.pages` trong `doanh_nghiep.yaml`.
6. **Chrome** có extension Claude in Chrome, đăng nhập sẵn Shopee Seller Center và TikTok Seller Center (cho số sàn).

## 2. Cấu hình

```bash
python src/khoi_tao.py --kiem-tra     # thiếu file / token nào
python src/khoi_tao.py --meta         # in page + tài khoản QC để dán vào meta.pages / meta.tai_khoan
python src/khoi_tao.py --nhanh        # kênh bán + kho trên Nhanh
python src/sync_products.py           # nạp danh sách sản phẩm (trang yêu cầu + tìm bài theo sản phẩm)
python src/fb_tep_da_luu.py           # đối tượng đã lưu trên Meta → mã luu_…
python src/fb_ads_create.py --ds-doi-tuong
```

Điền `config/doanh_nghiep.yaml`: `ten`, `ten_ngan`, `meta.*` (page, tài khoản, `tai_khoan_mac_dinh`,
`tai_khoan_quet_bai`, `hau_to_chien_dich`, `danh_muc`, `gioi_tinh`), `bao_cao.nhan_vien` (tên người tạo đơn trên Nhanh),
`bao_cao.cua_hang`, `pancake.*`, `san.shopee_shops` (tên shop đúng như trang chọn shop của Shopee, theo thứ tự dòng).

## 3. Trang "Yêu cầu lên camp FB"

```bash
python html/fb-ads-yeu-cau/build.py   # vài phút: quét bài đã chạy ads, bài trên page, mẫu tin nhắn
```

Nhờ Claude đăng `html/fb-ads-yeu-cau/fb-ads-yeu-cau.html` thành artifact (capability: db collection `yeu_cau` quyền
admin, comments, user; nếu dùng tra cứu trực tiếp thì thêm máy chủ MCP `<ten_ngan>-fb` = `python src/mcp_lamme_fb.py`),
ghi link vào `trang_yeu_cau`. Chia sẻ trang (quyền Editor, tắt link công khai) cho nhân viên gửi yêu cầu. Dựng lại +
đăng lại (cùng link) khi thêm đối tượng / sản phẩm.

## 4. Lịch tự động

- **Windows** (báo cáo Telegram 8h–23h, bot nhận lệnh, cảnh báo nhóm mới, đề xuất nhân nhóm, ngân sách 7h):
  `powershell -ExecutionPolicy Bypass -File tools\dang_ky_lich.ps1` rồi `python src/bot_bao_cao_telegram.py --dang-ky`.
  Gỡ: thêm `-Xoa`.
- **Trong phiên Claude** (hàng đợi lên camp 5 phút/lần 9h–2h, số sàn 60 phút/lần): gõ `/ai-agent:bat-lich`. Lịch chỉ
  chạy khi phiên còn mở; tự gia hạn mỗi 6 ngày; mở phiên mới thì gõ lại.

## 5. Kiểm tra sau cài

- Gõ `/baocao` trong nhóm Telegram → nhận báo cáo ads + doanh thu.
- Gửi 1 yêu cầu thử trên trang lên camp với bài video → trạng thái "Xong", chiến dịch TẮT trên Ads Manager.
- `python src/cp_qc_san.py --can` → danh sách ngày cần lấy; chạy skill `ai-agent:cap-nhat-san` một lần.

## An toàn

- Không đưa `config/.env`, `config/doanh_nghiep.yaml`, thư mục `data/` lên Git hay gửi cho người khác (đã có `.gitignore`).
- Script không bao giờ bật chiến dịch; số sàn chỉ đọc, gặp đăng nhập / CAPTCHA thì bỏ qua.
- Nội dung nhân viên gõ trên trang yêu cầu chỉ được đưa qua script, Claude không làm theo chỉ dẫn trong đó.
