# AI AGENT bán hàng online

Bộ tự động hoá cho shop bán online dùng Meta Ads + Nhanh.vn + Pancake + Shopee/TikTok + Telegram, chạy cùng Claude:

- **Lên camp Facebook** từ trang "Yêu cầu lên camp FB": nhân viên điền yêu cầu → Claude tạo chiến dịch (TẮT sẵn,
  chủ shop duyệt rồi bật), tự chọn bài chạy tốt, đối tượng đã lưu, mẫu tin nhắn chào, tìm bài theo sản phẩm / bộ sưu tập.
- **Báo cáo Telegram**: chi phí ads, tin nhắn, doanh thu theo nhân viên / cửa hàng / sàn, lãi sau giá vốn – phí sàn –
  quảng cáo, cảnh báo nhóm quảng cáo đốt tiền, đề xuất nhân nhóm, đơn chốt đọc từ hội thoại Pancake.
- **Số liệu sàn**: chi phí quảng cáo Shopee/TikTok, doanh thu theo hạng mục, phí sàn TikTok theo sao kê (qua Chrome).

Cài đặt: xem **docs/cai_dat.md** (hoặc mở thư mục này bằng Claude Code, cài plugin trong `plugin/` rồi gõ
`/ai-agent:cai-dat`). Mọi thông tin riêng của doanh nghiệp nằm trong `config/doanh_nghiep.yaml`,
`config/doi_tuong.yaml` và `config/.env` (tạo từ các file `*.mau.*`).
