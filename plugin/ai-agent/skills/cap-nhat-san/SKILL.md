---
name: cap-nhat-san
description: Cập nhật số liệu sàn cho báo cáo Telegram qua Claude in Chrome (đã đăng nhập sẵn) — chi phí quảng cáo Shopee/TikTok theo ngày, doanh thu theo hạng mục (thẻ SP/Live/Video/Affiliate), sao kê phí sàn TikTok. Dùng khi lịch "cập nhật CP QC sàn" chạy hoặc khi được nhờ lấy lại số sàn.
---

# Cập nhật số liệu sàn (Shopee, TikTok)

Làm trong thư mục code AI AGENT. Shop Shopee lấy từ `san.shopee_shops` trong `config/doanh_nghiep.yaml` (đúng thứ tự
dòng ở trang chọn shop); có TikTok khi `san.co_tiktok: true`. Đặt `PYTHONIOENCODING=utf-8` khi chạy python.

## Quy tắc an toàn
- **Chỉ đọc số liệu.** Không bấm gì khác trên trang người bán (không đổi chiến dịch, ngân sách, không bấm "Xuất").
- Trang đòi đăng nhập / CAPTCHA / xác minh mật khẩu / lỗi quyền → bỏ qua sàn hoặc bước đó, **không tự đăng nhập**.
- Mở tab riêng, xong đóng hết tab đã mở. Kết quả javascript_tool dài bị cắt → lấy chuỗi theo từng đoạn.

## Bước 1 — cần lấy gì
`python src/cp_qc_san.py --can`. Có `"tam_dung"` (nhóm Telegram gõ /offchiphisan) → trả lời đúng 1 dòng
"CP QC sàn đang tạm dừng (/offchiphisan)." rồi dừng, không mở Chrome. Không thì có danh sách ngày CP QC theo shop.
Chạy thêm `python src/hang_muc_san.py --can` (ngày doanh thu hạng mục) và `python src/phi_san_tiktok.py --can` (`{"tu"}`).

## Bước 2 — Shopee (mỗi shop có ngày cần lấy)
1. Mở `https://banhang.shopee.vn/portal/shop`, chụp màn hình, bấm "Chi tiết" **theo toạ độ** ở đúng dòng tên shop
   (bấm theo ref không ăn), chờ ~5 giây. Kiểm `fetch('/api/selleraccount/shop_info/')` trả đúng tên shop.
   Lần chụp thứ 2 trong cùng tab có thể treo — bỏ chụp, bấm đúng toạ độ cũ rồi kiểm tên shop.
2. CP QC: nạp nguyên nội dung `src/cp_qc_san_js/shopee.js` bằng javascript_tool, `await window.__cpqcShopeeChay([ngày])`;
   `loi` rỗng → chuỗi `Object.entries(kq.ngay).map(([d,v])=>d.slice(5)+':'+Math.round(v.tong)).join(';')` →
   `python src/cp_qc_san.py --shopee "<tên shop>" "<chuỗi>"`.
3. Hạng mục: nạp `src/hang_muc_san_js/shopee.js`, `window.__hmShopeeChay([ngày])`, chờ `window.__hmShopeeKQ.xong`;
   chuỗi `d.slice(5)+':'+[v.tong,v.the,v.live,v.video,v.aff].map(Math.round).join(':')` nối `;` →
   `python src/hang_muc_san.py --shopee "<tên shop>" "<chuỗi>"`. "permission denied" = tài khoản phụ không có quyền
   Phân tích bán hàng → bỏ qua, ghi 1 dòng trong báo cáo.

## Bước 3 — TikTok
1. Mở `https://seller-vn.tiktok.com/ads-creation/dashboard?origin=SC_ads_tab_button_PC`, chạy ngay
   `performance.setResourceTimingBufferSize(5000)`, chờ ~10 giây (đợi tới khi có request `oec/stat/post_campaign_list`).
2. CP QC: nạp `src/cp_qc_san_js/tiktok.js`, `await window.__cpqcTikTokChay([ngày])`; chuỗi
   `d.slice(5)+':'+Math.round(v.product)+':'+Math.round(v.live)` nối `;` → `python src/cp_qc_san.py --tiktok "<chuỗi>"`.
3. Hạng mục: nạp `src/hang_muc_san_js/tiktok.js`, `window.__hmTikTokChay([ngày])` (chậm ~1,5 giây/ngày); chuỗi
   `d.slice(5)+':'+[v.tong,v.live,v.video,v.the].map(Math.round).join(':')` → `python src/hang_muc_san.py --tiktok "<chuỗi>"`.
4. Sao kê phí: mở `https://seller-vn.tiktok.com/finance/bills?tab=statements`, chạy ngay
   `performance.setResourceTimingBufferSize(5000)`, chờ ~8 giây; nạp `src/cp_qc_san_js/tiktok_sao_ke.js`,
   `await window.__skTikTokChay('<tu>')`; chuỗi `d.slice(5)+':'+[v.dt,v.phi,v.dc].map(Math.round).join(':')` →
   `python src/phi_san_tiktok.py --luu "<chuỗi>"`.

## Báo cáo
Đúng 1 dòng: số đã cập nhật (CP QC từng shop/TikTok hôm nay, hạng mục, tỉ lệ phí TikTok 30 ngày) và phần bị bỏ qua + lý do.
