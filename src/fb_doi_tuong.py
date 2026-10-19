"""Danh sách đối tượng chọn được khi lên chiến dịch (dùng bởi fb_ads_create.py).

Nội dung nằm ở config/doi_tuong.yaml (riêng từng doanh nghiệp — đóng gói AI AGENT 19/10/2026); file này đọc YAML và
đổi tên tài khoản QC trong "tep" / "loai_tru_da_mua" sang ID tài khoản (config/doanh_nghiep.yaml → meta.tai_khoan).

Trường mỗi đối tượng:
    ten_nhom    hậu tố tên nhóm: "<TÊN SP> - <ten_nhom>"
    mo_ta       hiện ra khi xem danh sách
    tuoi        (min, max)
    goi_y       (min, max) gợi ý độ tuổi cho Advantage+ (chỉ khi adv=1)
    adv         1 = bật Advantage+ Audience (Meta được mở rộng ra ngoài đối tượng)
    so_thich    flexible_spec — các nhóm trong 1 dict là HOẶC
    tep         tệp đối tượng tuỳ chỉnh / lookalike theo từng tài khoản (ID khác nhau giữa các tài khoản)
    ngan_sach   ngân sách mặc định/ngày
"""
import cau_hinh

_TK = cau_hinh.lay("meta.tai_khoan", {}) or {}


def _id_tk(ten: str) -> str:
    """'lamme3' → ID tài khoản; đã là ID thì giữ nguyên."""
    return str(_TK.get(ten, ten))


def _nap() -> tuple[dict, list, set, dict]:
    y = cau_hinh.doi_tuong()
    dt = {}
    for ma, v in (y.get("doi_tuong") or {}).items():
        v = dict(v)
        for k in ("tuoi", "goi_y"):
            if k in v:
                v[k] = tuple(v[k])
        if "tep" in v:
            v["tep"] = {_id_tk(tk): ds for tk, ds in v["tep"].items()}
        dt[ma] = v
    ltdm = {_id_tk(tk): ds for tk, ds in (y.get("loai_tru_da_mua") or {}).items()}
    return dt, list(y.get("mac_dinh") or []), set(y.get("khong_loai_tru") or []), ltdm


DOI_TUONG, MAC_DINH, KHONG_LOAI_TRU, LOAI_TRU_DA_MUA = _nap()
# Cột loai_tru = 1: loại người đã mua 90 ngày khỏi các nhóm KHÔNG phải bám đuổi (KHONG_LOAI_TRU); tài khoản không có
# tệp trong LOAI_TRU_DA_MUA thì bỏ qua loại trừ (có cảnh báo).

# Đối tượng đã lưu trên Meta (chủ trang thêm 10/10/2026) — đọc cache data/fb_tep_da_luu.json, mã "luu_…"; lấy lại
# bằng `python src/fb_tep_da_luu.py` (trang "Yêu cầu lên camp FB" dựng lại cũng tự lấy). Mã viết tay được ưu tiên.
try:
    from fb_tep_da_luu import doi_tuong as _doi_tuong_meta
    for _ma, _dt in _doi_tuong_meta().items():
        DOI_TUONG.setdefault(_ma, _dt)
except Exception:  # noqa: BLE001 — cache hỏng không được làm hỏng việc lên camp
    pass
