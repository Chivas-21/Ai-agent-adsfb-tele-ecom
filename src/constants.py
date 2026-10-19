"""Hằng số Nhanh v3 (https://apidocs.nhanh.vn/v3/modelconstant.md) + quy tắc gom kênh thương mại."""

SALE_CHANNELS = {
    1: "Admin", 2: "Website", 10: "API", 20: "Facebook", 21: "Instagram",
    41: "Lazada", 42: "Shopee", 43: "Sendo", 45: "Tiki", 48: "Tiktok Shop",
    49: "Zalo OA", 50: "Shopee chat", 51: "Lazada chat", 52: "Zalo cá nhân",
}

ORDER_STATUS = {
    40: "Đã đóng gói", 42: "Đang đóng gói", 43: "Chờ thu gom", 54: "Đơn mới",
    55: "Đang xác nhận", 56: "Đã xác nhận", 57: "Chờ khách xác nhận",
    58: "Hãng vận chuyển hủy đơn", 59: "Đang chuyển", 60: "Thành công",
    61: "Thất bại", 63: "Khách hủy", 64: "Hệ thống hủy", 68: "Hết hàng",
    71: "Đang chuyển hoàn", 72: "Đã chuyển hoàn", 73: "Đổi kho xuất hàng", 74: "Xác nhận hoàn",
}

# Nhóm trạng thái dùng cho số liệu thương mại:
#   success   = đã giao thành công (doanh thu chắc chắn)
#   in_flight = đã chốt, đang xử lý/giao (doanh thu booked, có thể còn hủy/hoàn)
#   cancelled = hủy trước khi giao (không tính)
#   returned  = hoàn hàng (không tính doanh thu, dùng để tính tỷ lệ hoàn)
STATUS_GROUP = {
    60: "success",
    40: "in_flight", 42: "in_flight", 43: "in_flight", 54: "in_flight", 55: "in_flight",
    56: "in_flight", 57: "in_flight", 59: "in_flight", 73: "in_flight",
    58: "cancelled", 61: "cancelled", 63: "cancelled", 64: "cancelled", 68: "cancelled",
    71: "returned", 72: "returned", 74: "returned",
}

# Loại đơn không phải bán hàng (khách trả lại, chuyển kho)
NON_SALE_ORDER_TYPES = (14, 15)

import cau_hinh  # noqa: E402

DEPOTS = {int(k): v for k, v in (cau_hinh.lay("nhanh.kho") or {}).items()}   # config/doanh_nghiep.yaml

# Dòng đơn có giá bán thực/chiếc dưới ngưỡng này là hàng tặng kèm (thiếp, túi, khăn, sản phẩm tặng):
# vẫn tính doanh thu/giá vốn của đơn, nhưng không tính là "chiếc bán" của mẫu
GIFT_MAX_UNIT_PRICE = 20000

# Mẫu có >= 50% số chiếc là hàng tặng (thiếp, túi...) được coi là quà tặng kèm: không lập đề bài bán
GIFT_HEAVY_SHARE = 0.5


def commercial_channel(sale_channel_id: int | None, traffic_source: str | None) -> str:
    """Gom kênh Nhanh về kênh thương mại. Đơn tạo từ Admin nhưng nguồn Facebook -> Facebook."""
    if sale_channel_id in (42, 50):
        return "Shopee"
    if sale_channel_id == 48:
        return "TikTok Shop"
    if sale_channel_id in (20, 21):
        return "Facebook"
    if sale_channel_id in (41, 51):
        return "Lazada"
    if sale_channel_id in (49, 52):
        return "Zalo"
    source = (traffic_source or "").lower()
    if "facebook" in source or "fb" in source or "instagram" in source:
        return "Facebook"
    if "zalo" in source:
        return "Zalo"
    if sale_channel_id == 2 or "website" in source:
        return "Website"
    return "Admin/Khác"
