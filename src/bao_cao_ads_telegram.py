"""Báo cáo kết quả chạy Facebook Ads gửi về Telegram.

Lấy số liệu từ Marketing API (insights, cấp chiến dịch) của các tài khoản QC Lamme trong
fb_ads_create.TAI_KHOAN, gộp lại và gửi 1 tin nhắn: tổng chi tiêu / trò chuyện / lượt mua,
theo tài khoản, và top chiến dịch chi nhiều nhất.

Cần trong config/.env:  META_ACCESS_TOKEN (đã có), TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.

Chạy:
    python src/bao_cao_ads_telegram.py                    # hôm qua
    python src/bao_cao_ads_telegram.py --ngay hom-nay     # hôm nay (tới giờ)
    python src/bao_cao_ads_telegram.py --ngay 7           # 7 ngày qua
    python src/bao_cao_ads_telegram.py --ngay thang-nay   # tháng này (ngày 1 tới hiện tại)
    python src/bao_cao_ads_telegram.py --dry-run          # in ra màn hình, không gửi
"""
import argparse
import html
import os
import sys
from datetime import date, datetime, timedelta

import requests

import cau_hinh
import fb_ads_create as fb
from constants import STATUS_GROUP
from nhanh_client import VN_TZ, NhanhClient

TOP = 0  # số chiến dịch hiển thị (0 = không liệt kê)
LOAI_TRO_CHUYEN = "onsite_conversion.messaging_conversation_started_7d"
LOAI_MUA = ("onsite_conversion.messaging_purchase", "omni_purchase", "purchase")


def khoang_ngay(chon: str) -> tuple[str, str, str]:
    h = date.today()
    if chon == "hom-nay":
        return h.isoformat(), h.isoformat(), f"hôm nay {h:%d/%m} (số liệu đến {datetime.now(VN_TZ):%H:%M})"
    if chon == "hom-qua":
        d = h - timedelta(days=1)
        return d.isoformat(), d.isoformat(), f"hôm qua {d:%d/%m}"
    if chon == "thang-truoc":  # trọn tháng trước
        cuoi = h.replace(day=1) - timedelta(days=1)
        dau = cuoi.replace(day=1)
        return dau.isoformat(), cuoi.isoformat(), f"tháng {cuoi:%m/%Y} ({dau:%d/%m}–{cuoi:%d/%m})"
    if chon == "thang-nay":  # từ ngày 1 tới hiện tại (gồm hôm nay)
        a = h.replace(day=1)
        return a.isoformat(), h.isoformat(), (f"tháng {h:%m/%Y} ({a:%d/%m}–{h:%d/%m}, "
                                              f"số liệu đến {datetime.now(VN_TZ):%H:%M})")
    n = int(chon)
    a, b = h - timedelta(days=n), h - timedelta(days=1)
    return a.isoformat(), b.isoformat(), f"{n} ngày qua ({a:%d/%m}–{b:%d/%m})"


def _hanh_dong(row: dict, loai) -> float:
    loai = (loai,) if isinstance(loai, str) else loai
    for l in loai:  # lấy loại đầu tiên có số liệu, tránh cộng trùng giữa các loại mua hàng
        for a in row.get("actions", []):
            if a["action_type"] == l:
                return float(a["value"])
    return 0.0


def lay_so_lieu(tu: str, den: str) -> list[dict]:
    out = []
    for ten, acc in fb.TAI_KHOAN.items():
        try:
            kq = fb._goi("GET", f"act_{acc}/insights", {
                "level": "campaign",
                "fields": "campaign_name,spend,actions",
                "time_range": {"since": tu, "until": den},
                "limit": 500,
            })
        except RuntimeError as e:
            print(f"[{ten}] bỏ qua: {e}", file=sys.stderr)
            continue
        rows = kq.get("data", [])
        while kq.get("paging", {}).get("next"):
            kq = requests.get(kq["paging"]["next"], timeout=60).json()
            rows += kq.get("data", [])
        for r in rows:
            out.append({
                "tk": ten,
                "camp": r.get("campaign_name", ""),
                "chi": float(r.get("spend", 0)),
                "tc": _hanh_dong(r, LOAI_TRO_CHUYEN),
                "mua": _hanh_dong(r, LOAI_MUA),
            })
    return out


# Chỉ báo doanh thu của 3 nhân viên bán hàng này (chủ trang chốt 03/10/2026) — bỏ cửa hàng, CSKH, booking, Shopee…
NHAN_VIEN_BAO_CAO = tuple(cau_hinh.lay("bao_cao.nhan_vien") or ())   # config/doanh_nghiep.yaml


def _chi_nv_bao_cao(nv: list[dict]) -> list[dict]:
    chon = {t.casefold() for t in NHAN_VIEN_BAO_CAO}
    return [a for a in nv if a["ten"].strip().casefold() in chon]


# Doanh thu bán lẻ tại cửa hàng (hoá đơn bán lẻ, không phải đơn hàng) theo người lập phiếu — chủ trang chốt 03/10/2026
CUA_HANG_BAO_CAO = tuple(cau_hinh.lay("bao_cao.cua_hang") or ())


def doanh_thu_ban_le(tu: str, den: str) -> list[dict]:
    """Hoá đơn bán lẻ Nhanh (bill/retail) theo NGƯỜI LẬP PHIẾU, chỉ CUA_HANG_BAO_CAO.

    Doanh thu = khớp cột "Doanh thu + VAT theo người lập phiếu" của báo cáo Bán lẻ › Theo nhân viên trên web Nhanh
    (= Tổng bán − Chiết khấu − Tổng trả): Σ payment.amount phiếu xuất bán (type 2) − Σ phiếu trả lại bán lẻ
    (type 1, related.type 6). Kiểm 01–03/10/2026: HN 38.814.000đ, HCM 21.093.000đ — đúng như web.
    API chỉ cho lấy tối đa 31 ngày mỗi lần → chia khoảng.
    """
    chon = {t.casefold() for t in CUA_HANG_BAO_CAO}
    d0, d1 = date.fromisoformat(tu), min(date.fromisoformat(den), date.today())
    kq: dict[str, dict] = {}
    client = NhanhClient()
    while d0 <= d1:
        cuoi = min(d0 + timedelta(days=30), d1)
        for b in client.paginate("bill/retail", {"fromDate": d0.isoformat(), "toDate": cuoi.isoformat()}):
            ten = ((b.get("created") or {}).get("name") or (b.get("sale") or {}).get("name") or "").strip()
            if ten.casefold() not in chon:
                continue
            a = kq.setdefault(ten, {"ten": ten, "don": 0, "tra": 0, "sp": 0, "dt": 0.0, "dt_ban": 0.0, "dt_tra": 0.0,
                                    "_sl": {}})
            tien = (b.get("payment") or {}).get("amount") or 0
            so_sp = sum(p.get("quantity") or 0 for p in b.get("products") or [])
            dau = 1 if b.get("type") == 2 else -1 if b.get("type") == 1 and (b.get("related") or {}).get("type") == 6 else 0
            for p in b.get("products") or []:   # số lượng thuần theo mã → giá vốn (tra sau)
                if p.get("id"):
                    a["_sl"][p["id"]] = a["_sl"].get(p["id"], 0) + dau * (p.get("quantity") or 0)
            if b.get("type") == 2:
                a["don"] += 1
                a["sp"] += so_sp
                a["dt"] += tien
                a["dt_ban"] += tien
            elif b.get("type") == 1 and (b.get("related") or {}).get("type") == 6:  # khách trả lại hàng bán lẻ
                a["tra"] += 1
                a["sp"] -= so_sp
                a["dt"] -= tien
                a["dt_tra"] += tien
        d0 = cuoi + timedelta(days=1)
    # Giá vốn bán lẻ: hoá đơn không có giá vốn → giá vốn bình quân hiện tại của mã (product/list prices.avgCost)
    ids = sorted({i for a in kq.values() for i in a["_sl"]})
    gia_von: dict[int, float] = {}
    for k in range(0, len(ids), 100):
        for p in client.call("product/list", {"filters": {"ids": ids[k:k + 100]}, "paginator": {"size": 100}}).get("data") or []:
            gia_von[p["id"]] = (p.get("prices") or {}).get("avgCost") or 0
    for a in kq.values():
        a["gv"] = sum(sl * gia_von.get(i, 0) for i, sl in a.pop("_sl").items())
    return sorted(kq.values(), key=lambda a: -a["dt"])


# Kênh sàn trên Nhanh (channel.saleChannel): 42 Shopee, 50 Shopee chat → Shopee; 48 TikTok Shop
KENH_SAN = {int(k): v for k, v in (cau_hinh.lay("nhanh.kenh_san") or {}).items()}
# Đơn hoàn tạo SAU khi đơn sàn đã giao thành công: Nhanh tạo đơn mới loại 14 (Khách trả lại hàng) / 16 (Đơn hoàn
# một phần), trỏ về đơn gốc qua info.originalOrderId — đơn gốc vẫn "Thành công" (chủ trang chỉ ra 04/10/2026).
LOAI_DON_HOAN = (14, 16)
_NHO: dict = {}   # (tu, den) → (lúc, kết quả) — 1 báo cáo gọi cả nhân viên lẫn sàn chỉ lấy đơn 1 lần


# Phí sàn: businessPayment (tiền sàn trả shop) chỉ là số tạm cho tới khi sàn quyết toán (~1–2 tuần sau giao) — đơn
# TikTok mới ra phí ~3% trong khi đơn đã quyết toán ~26% (kiểm 06/10/2026). Nên chỉ lấy phí THẬT của đơn thành công
# tạo trước NGAY_QUYET_TOAN ngày; đơn còn lại ước tính = tiền hàng × tỉ lệ phí thật (data/ty_le_phi_san.json, cập nhật
# mỗi khi 1 kỳ có ≥ 100 đơn đã quyết toán; chưa có thì dùng TY_LE_PHI_MAC_DINH đo trên 10–12/09/2026).
NGAY_QUYET_TOAN = 10
TY_LE_PHI_MAC_DINH = dict(cau_hinh.lay("bao_cao.ty_le_phi_mac_dinh") or {"Shopee": 0.3, "TikTok Shop": 0.25})
# TikTok: từ ~26/09/2026 Nhanh không còn ghi tiền quyết toán thật — businessPayment đứng ở ~96,5% tiền hàng dù đơn đã
# giao lâu (báo cáo ra phí 3,6%, chủ trang hỏi 16/10). Đơn có phí < ngưỡng này coi như CHƯA quyết toán → ước tính theo
# tỉ lệ phí sao kê TikTok 30 ngày (phi_san_tiktok.py, lấy qua Chrome cùng lượt CP QC sàn). Đơn đã quyết toán thật ~25%.
NGUONG_PHI_THAT = {"TikTok Shop": 0.10}


def _file_ty_le():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent / "data" / "ty_le_phi_san.json"


def ty_le_phi(kenh: str, den: str | None = None) -> float:
    import json
    if kenh == "TikTok Shop":
        import phi_san_tiktok
        r = phi_san_tiktok.ty_le(den)
        if r:
            return r
    try:
        return json.loads(_file_ty_le().read_text(encoding="utf-8"))[kenh]["ty_le"]
    except (OSError, ValueError, KeyError):
        return TY_LE_PHI_MAC_DINH.get(kenh, 0.3)


def _luu_ty_le(san: dict) -> None:
    import json
    try:
        d = json.loads(_file_ty_le().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    doi = False
    for kenh, k in san.items():
        if k.get("don_that", 0) >= 100 and k.get("dt_that", 0) > 0:
            d[kenh] = {"ty_le": round(k["phi_that"] / k["dt_that"], 4), "so_don": k["don_that"],
                       "luc": datetime.now(VN_TZ).strftime("%d/%m/%Y")}
            doi = True
    if doi:
        _file_ty_le().write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _gia_von(o: dict) -> float:
    """Giá vốn đơn = Σ avgCost × số lượng (giá vốn bình quân Nhanh ghi trong từng dòng sản phẩm của đơn)."""
    return sum((p.get("avgCost") or 0) * (p.get("quantity") or 0) for p in o.get("products") or [])


def so_lieu_nhanh(tu: str, den: str) -> dict:
    """1 lượt lấy đơn Nhanh (theo ngày tạo, bỏ đơn hủy) → {"nv": [...], "san": [...]}.

    nv:  doanh thu theo NGƯỜI TẠO ĐƠN = Tổng thu (codAmount) + Tiền chuyển khoản, chỉ NHAN_VIEN_BAO_CAO.
         Gán theo người tạo đơn kể cả khi NV bán là người khác (chốt 03/10/2026); đơn createdById 0 (sàn/API) bỏ.
    san: doanh thu Shopee / TikTok Shop = đơn tạo trong kỳ − đơn huỷ − đơn hoàn; tiền = tiền hàng sau giảm giá
         (Σ products.totalAmount, đã gồm VAT, bằng Tổng thu của đơn sàn); chia theo shop.
    """
    import time
    khoa = (tu, den)
    if khoa in _NHO and time.time() - _NHO[khoa][0] < 120:
        return _NHO[khoa][1]
    t0 = datetime.fromisoformat(tu).replace(tzinfo=VN_TZ)
    t1 = datetime.fromisoformat(den).replace(tzinfo=VN_TZ) + timedelta(days=1)
    t1 = min(t1, datetime.now(VN_TZ))
    nv: dict[str, dict] = {}
    san: dict[str, dict] = {}
    goc_san: dict[int, tuple[str, str]] = {}   # id đơn sàn đã cộng → (kênh, shop), để trừ đơn hoàn tạo về sau
    client = NhanhClient()
    bay_gio_ts = datetime.now(VN_TZ).timestamp()
    for o in client.list_orders(t0, t1):
        i = o["info"]
        if STATUS_GROUP.get(i["status"]) == "cancelled":
            continue
        so_sp = sum(p.get("quantity", 0) for p in o.get("products") or [])
        kenh = KENH_SAN.get((o.get("channel") or {}).get("saleChannel"))
        # sàn: bỏ đơn hoàn (trạng thái hoàn) và chính các đơn hoàn sau giao (loại 14/16/17) — chốt 04/10/2026
        if kenh and STATUS_GROUP.get(i["status"]) != "returned" and i.get("type") not in (*LOAI_DON_HOAN, 17):
            k = san.setdefault(kenh, {"kenh": kenh, "don": 0, "sp": 0, "dt": 0.0, "shop": {}, "hoan": 0, "tien_hoan": 0.0,
                                      "gv": 0.0, "phi": 0.0, "phi_that": 0.0, "dt_that": 0.0, "don_that": 0,
                                      "dt_uoc": 0.0, "don_uoc": 0})
            tien = sum(p.get("totalAmount") or 0 for p in o.get("products") or [])
            k["don"] += 1
            k["sp"] += so_sp
            k["dt"] += tien
            k["gv"] += _gia_von(o)
            # phí sàn = tiền hàng − tiền sàn trả shop (businessPayment) — chỉ tin số của đơn đã quyết toán
            bp = (o.get("payment") or {}).get("businessPayment")
            da_qt = (STATUS_GROUP.get(i["status"]) == "success" and bp
                     and (i.get("createdAt") or 0) <= bay_gio_ts - NGAY_QUYET_TOAN * 86400
                     and tien - bp >= tien * NGUONG_PHI_THAT.get(kenh, 0))
            if da_qt:
                k["phi_that"] += max(tien - bp, 0)
                k["dt_that"] += tien
                k["don_that"] += 1
            else:
                k["dt_uoc"] += tien
                k["don_uoc"] += 1
            shop = ((o.get("channel") or {}).get("shopName") or "?").strip()
            k["shop"][shop] = k["shop"].get(shop, 0) + tien
            goc_san[i["id"]] = (kenh, shop)
        ten = (i.get("createdByName") or "").strip() or (i.get("saleName") if i.get("createdById") and
                                                        i.get("createdById") == i.get("saleId") else "")
        if not i.get("createdById") or not ten:
            continue
        a = nv.setdefault(ten, {"ten": ten, "don": 0, "sp": 0, "dt": 0.0, "gv": 0.0})
        a["don"] += 1
        if STATUS_GROUP.get(i["status"]) != "returned":   # đơn hoàn: hàng về kho, không tính giá vốn
            a["gv"] += _gia_von(o)
        pay = o.get("payment") or {}
        a["dt"] += (pay.get("codAmount") or 0) + (pay.get("transfer") or {}).get("amount", 0)
        a["sp"] += so_sp
    # Trừ đơn hoàn sau giao thành công: đơn loại 14/16 tạo từ đầu kỳ tới nay, trỏ về đơn gốc đã cộng ở trên
    bay_gio = datetime.now(VN_TZ)
    for loai in LOAI_DON_HOAN:
        dau = t0
        while dau < bay_gio:
            cuoi = min(dau + timedelta(days=30), bay_gio)
            for o in client.paginate("order/list", {"createdAtFrom": int(dau.timestamp()), "createdAtTo": int(cuoi.timestamp()),
                                                    "type": loai, "saleChannels": sorted(KENH_SAN)}, size=100):
                i = o["info"]
                goc = goc_san.get(i.get("originalOrderId"))
                if not goc or STATUS_GROUP.get(i["status"]) == "cancelled":
                    continue
                kenh, shop = goc
                tien = sum(p.get("totalAmount") or 0 for p in o.get("products") or [])
                k = san[kenh]
                k["dt"] -= tien
                k["sp"] -= sum(p.get("quantity", 0) for p in o.get("products") or [])
                k["hoan"] += 1
                k["tien_hoan"] += tien
                k["gv"] -= _gia_von(o)   # hàng khách trả về kho
                k["shop"][shop] = k["shop"].get(shop, 0) - tien
            dau = cuoi
    _luu_ty_le(san)
    for kenh, k in san.items():   # phí sàn = phí thật (đơn đã quyết toán) + ước tính phần còn lại
        k["ty_le_phi"] = ty_le_phi(kenh, den)
        k["phi"] = k["phi_that"] + k["dt_uoc"] * k["ty_le_phi"]
    kq = {"nv": _chi_nv_bao_cao(sorted(nv.values(), key=lambda a: -a["dt"])),
          "san": sorted(san.values(), key=lambda k: -k["dt"]),
          "ban_le": doanh_thu_ban_le(tu, den)}
    _NHO[khoa] = (time.time(), kq)
    return kq


def doanh_thu_nhan_vien(tu: str, den: str) -> list[dict]:
    return so_lieu_nhanh(tu, den)["nv"]


def doanh_thu_san(tu: str, den: str) -> list[dict]:
    return so_lieu_nhanh(tu, den)["san"]


def so_lieu_nhanh_cache(tu: str, den: str, gio: float = 6) -> dict:
    """Như so_lieu_nhanh nhưng lưu kết quả `gio` giờ cho khoảng ngày đã kết thúc (tháng trước…) —
    lấy cả tháng từ Nhanh mất ~2,5 phút. Khoảng có hôm nay luôn lấy mới."""
    import json
    import time
    from pathlib import Path
    if den >= date.today().isoformat():
        return so_lieu_nhanh(tu, den)
    f = Path(__file__).resolve().parent.parent / "data" / "nhanh_cache_v9.json"  # v9: phí TikTok theo sao kê (16/10/2026)
    try:
        kho = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kho = {}
    khoa = f"{tu}_{den}"
    if khoa in kho and time.time() - kho[khoa]["luc"] < gio * 3600:
        kq = kho[khoa]["kq"]
        return {"nv": _chi_nv_bao_cao(kq["nv"]), "san": kq["san"], "ban_le": kq.get("ban_le", [])}
    kq = so_lieu_nhanh(tu, den)
    kho[khoa] = {"luc": time.time(), "kq": kq}
    f.write_text(json.dumps(kho, ensure_ascii=False), encoding="utf-8")
    return kq


def doanh_thu_nhan_vien_cache(tu: str, den: str) -> list[dict]:
    return so_lieu_nhanh_cache(tu, den)["nv"]


def vnd(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".") + "đ"


def gia(chi: float, n: float) -> str:
    return vnd(chi / n) if n else "–"


def cp_qc_san(tu: str, den: str) -> dict | None:
    """Chi phí QC sàn (Shopee Ads, TikTok GMV Max) trong [tu, den] từ data/cp_qc_san.json — Claude lấy qua Chrome
    theo lịch (src/cp_qc_san.py). Chưa có số / lỗi → None (báo cáo vẫn gửi, chỉ thiếu dòng CP QC)."""
    try:
        import cp_qc_san
        kq = cp_qc_san.tong(tu, den)
    except Exception:  # noqa: BLE001
        return None
    return kq if kq.get("Shopee") is not None or kq.get("TikTok Shop") is not None else None


def hang_muc_san(tu: str, den: str) -> dict | None:
    """Doanh thu sàn theo hạng mục (Shopee: Thẻ SP / Live / Video / Affiliate; TikTok: Live / Video / Thẻ SP) trong
    [tu, den] từ data/hang_muc_san.json — Claude lấy qua Chrome cùng lịch CP QC sàn (src/hang_muc_san.py)."""
    try:
        import hang_muc_san
        kq = hang_muc_san.tong(tu, den)
    except Exception:  # noqa: BLE001
        return None
    return kq if kq.get("Shopee") or kq.get("TikTok Shop") else None


def _dong_hang_muc(hm: dict | None) -> list[str]:
    """Bảng doanh thu theo hạng mục cho /san (chủ trang thêm 10/10/2026)."""
    if not hm:
        return []
    import hang_muc_san
    dong = ["", "📊 <b>Doanh thu theo hạng mục</b> (số trên trang người bán)"]
    for san, hang, t in hang_muc_san.dong(hm):
        dong.append(f"{'🟠' if san == 'Shopee' else '🎵'} {san}: <b>{vnd(t)}</b>")
        dong += [f"    • {ten}: {vnd(v)} (" + f"{p:.1%}".replace(".", ",") + ")" for ten, v, p in hang]
    dong.append("<i>GMV đơn đặt theo sàn (gồm đơn sau này huỷ/hoàn) — để xem tỷ trọng, lệch với số Nhanh ở trên; "
                f"cập nhật {hm['luc']}" + (" — " + "; ".join(hm["thieu"]) if hm["thieu"] else "") + "</i>")
    return dong


def _cp(cp: float | None, dt: float) -> str:
    if cp is None:
        return ""
    return f" · CP QC <b>{vnd(cp)}</b>" + (f" ({cp / dt:.1%} DT)".replace(".", ",") if dt > 0 else "")


def _dong_san(san: list[dict], cp: dict | None = None) -> list[str]:
    """cp = cp_qc_san(tu, den): thêm chi phí QC sàn + % doanh thu (chủ trang yêu cầu 06/10/2026)."""
    e = html.escape
    dong = []
    for k in san:
        dong.append(f"• {e(k['kenh'])}: <b>{vnd(k['dt'])}</b> · {k['don']} đơn · {k['sp']:.0f} SP"
                    + (f" (đã trừ {k['hoan']} đơn hoàn sau giao {vnd(k['tien_hoan'])})" if k.get("hoan") else "")
                    + (_cp(cp.get(k["kenh"]), k["dt"]) if cp else ""))
        if len(k["shop"]) > 1:
            dong += [f"    – {e(s)}: {vnd(t)}" for s, t in sorted(k["shop"].items(), key=lambda x: -x[1])]
    if len(san) > 1:
        cp_tong = sum(cp.get(k["kenh"]) or 0 for k in san) if cp else None
        dong.append(f"Tổng: <b>{vnd(sum(k['dt'] for k in san))}</b> · {sum(k['don'] for k in san)} đơn"
                    + _cp(cp_tong, sum(k["dt"] for k in san)))
    if cp:
        dong.append(f"<i>CP QC sàn lấy từ trang người bán (Shopee Ads, TikTok GMV Max), cập nhật {cp['luc']}"
                    + (" — " + "; ".join(cp["thieu"]) if cp["thieu"] else "") + "</i>")
    return dong


def _dong_tong(nvien: list[dict] | None, ban_le: list[dict] | None, san: list[dict] | None) -> list[str]:
    """Dòng tổng doanh thu toàn bộ các kênh = 3 NV online + bán lẻ cửa hàng + sàn (chỉ những kênh có trong báo cáo)."""
    phan = [("NV online", sum(a["dt"] for a in nvien or [])), ("cửa hàng", sum(a["dt"] for a in ban_le or [])),
            ("sàn", sum(k["dt"] for k in san or []))]
    phan = [(t, v) for t, v in phan if v]
    if len(phan) < 2:
        return []
    # bỏ dòng chi tiết "NV online … + cửa hàng … + sàn …" (chủ trang yêu cầu 05/10/2026)
    return ["", f"💰 <b>Tổng doanh thu các kênh: {vnd(sum(v for _, v in phan))}</b>"]


def soan_san(san: list[dict], nhan: str, cp: dict | None = None, hm: dict | None = None) -> str:
    """Chỉ phần doanh thu sàn Shopee / TikTok Shop (lệnh bot /san); hm = hang_muc_san(tu, den)."""
    dau = f"🛍 <b>Doanh thu sàn Nhanh.vn — {html.escape(nhan)}</b>"
    if not san:
        return "\n".join([dau, "Không có đơn Shopee / TikTok Shop."] + _dong_hang_muc(hm))
    return "\n".join([dau] + _dong_san(san, cp) + ["Đơn tạo trong kỳ − đơn huỷ − đơn hoàn (kể cả phần hoàn sau giao) · tiền hàng sau giảm giá (đã gồm VAT)",
                                  "Tính theo đơn hàng Nhanh — có thể lệch vài % so với mục Tài chính sàn (sàn tính giá trị đơn khác)"]
                     + _dong_hang_muc(hm))


def soan_tin(rows: list[dict], nhan: str, nvien: list[dict] | None = None, san: list[dict] | None = None,
             ban_le: list[dict] | None = None, cp_san: dict | None = None) -> str:
    e = html.escape
    rows = [r for r in rows if r["chi"] > 0]
    if not rows:
        return f"📊 <b>Ads FB — {e(nhan)}</b>\nKhông có chi tiêu."
    chi, tc, mua = (sum(r[k] for r in rows) for k in ("chi", "tc", "mua"))
    dong = [
        f"📊 <b>Ads FB — {e(nhan)}</b>",
        f"💸 Chi tiêu: <b>{vnd(chi)}</b>",
        f"💬 Trò chuyện: <b>{tc:,.0f}</b> · giá/TC {gia(chi, tc)}",
        f"🛒 Lượt mua: <b>{mua:,.0f}</b> · giá/mua {gia(chi, mua)}",
        "",
        "<b>Theo tài khoản</b>",
    ]
    tk: dict[str, list[float]] = {}
    for r in rows:
        a = tk.setdefault(r["tk"], [0, 0, 0])
        a[0] += r["chi"]; a[1] += r["tc"]; a[2] += r["mua"]
    for t, (c, n, m) in sorted(tk.items(), key=lambda x: -x[1][0]):
        dong.append(f"• {e(t)}: {vnd(c)} · {n:,.0f} TC ({gia(c, n)}) · {m:,.0f} mua")
    if nvien:
        dong += ["", "<b>Doanh thu Nhanh.vn theo nhân viên</b>"]
        for a in nvien:
            dong.append(f"• {e(a['ten'])}: <b>{vnd(a['dt'])}</b> · {a['don']} đơn · {a['sp']:.0f} SP")
        dong.append(f"Tổng: <b>{vnd(sum(a['dt'] for a in nvien))}</b> · {sum(a['don'] for a in nvien)} đơn")
    if ban_le:
        dong += ["", "<b>Bán lẻ tại cửa hàng</b>"] + _dong_ban_le(ban_le)
    if san:
        dong += ["", "<b>Doanh thu sàn Nhanh.vn</b>"] + _dong_san(san, cp_san)
    dong += _dong_tong(nvien, ban_le, san)
    if TOP:
        dong += ["", f"<b>Top {TOP} chiến dịch chi nhiều nhất</b>"]
    for i, r in enumerate(sorted(rows, key=lambda r: -r["chi"])[:TOP], 1):
        dong.append(f"{i}. {e(r['camp'])}\n    {vnd(r['chi'])} · {r['tc']:,.0f} TC ({gia(r['chi'], r['tc'])}) · {r['mua']:,.0f} mua")
    return "\n".join(dong)


def _pt(x: float, dt: float) -> str:
    return f" ({x / dt:.1%})".replace(".", ",") if dt > 0 else ""


def soan_tai_chinh(rows: list[dict], nhan: str, nvien: list[dict], san: list[dict], ban_le: list[dict],
                   cp_san: dict | None = None) -> str:
    """/baocaotaichinh (chủ trang yêu cầu 06/10/2026): như /baocao + giá vốn, phí sàn, CP QC → lãi sau 3 khoản.

    Giá vốn: đơn hàng = Σ avgCost × SL ghi trong đơn (đơn hoàn không tính; sàn trừ hàng trả sau giao);
    bán lẻ = SL thuần × giá vốn bình quân hiện tại của mã. Phí sàn = tiền hàng − tiền sàn trả shop (businessPayment).
    CP QC = Ads FB (kênh nhân viên online) + Shopee Ads / TikTok GMV Max (cp_qc_san). Chưa trừ ship, lương, vận hành."""
    e = html.escape
    rows = [r for r in rows if r["chi"] > 0]
    chi, tc, mua = (sum(r[k] for r in rows) for k in ("chi", "tc", "mua"))
    dong = [f"📑 <b>Báo cáo tài chính — {e(nhan)}</b>", "",
            f"📊 <b>Ads FB</b>: chi <b>{vnd(chi)}</b> · {tc:,.0f} TC ({gia(chi, tc)}) · {mua:,.0f} mua ({gia(chi, mua)})"]
    tk: dict[str, list[float]] = {}
    for r in rows:
        a = tk.setdefault(r["tk"], [0, 0, 0])
        a[0] += r["chi"]; a[1] += r["tc"]; a[2] += r["mua"]
    for t, (c, n, m) in sorted(tk.items(), key=lambda x: -x[1][0]):
        dong.append(f"• {e(t)}: {vnd(c)} · {n:,.0f} TC ({gia(c, n)}) · {m:,.0f} mua")

    dt_nv, gv_nv = sum(a["dt"] for a in nvien), sum(a.get("gv", 0) for a in nvien)
    dong += ["", "👩‍💼 <b>Nhân viên online</b> (người tạo đơn)"]
    for a in nvien:
        dong.append(f"• {e(a['ten'])}: <b>{vnd(a['dt'])}</b> · {a['don']} đơn · GV {vnd(a.get('gv', 0))}")
    dong.append(f"Tổng: <b>{vnd(dt_nv)}</b> · GV {vnd(gv_nv)}{_pt(gv_nv, dt_nv)} · Ads FB {vnd(chi)}{_pt(chi, dt_nv)}")

    dt_bl, gv_bl = sum(a["dt"] for a in ban_le), sum(a.get("gv", 0) for a in ban_le)
    if ban_le:
        dong += ["", "🏬 <b>Bán lẻ tại cửa hàng</b>"]
        for a in ban_le:
            dong.append(f"• {e(a['ten'])}: <b>{vnd(a['dt'])}</b> · {a['don']} HĐ · GV {vnd(a.get('gv', 0))}")
        dong.append(f"Tổng: <b>{vnd(dt_bl)}</b> · GV {vnd(gv_bl)}{_pt(gv_bl, dt_bl)}")

    dt_s, gv_s, phi_s = (sum(k.get(x, 0) for k in san) for x in ("dt", "gv", "phi"))
    qc_s = sum((cp_san or {}).get(k["kenh"]) or 0 for k in san)
    if san:
        dong += ["", "🛍 <b>Sàn</b>"]
        for k in san:
            qc = (cp_san or {}).get(k["kenh"])
            dong.append(f"• {e(k['kenh'])}: <b>{vnd(k['dt'])}</b> · {k['don']} đơn\n"
                        f"    GV {vnd(k.get('gv', 0))}{_pt(k.get('gv', 0), k['dt'])} · phí sàn {vnd(k.get('phi', 0))}"
                        f"{_pt(k.get('phi', 0), k['dt'])}" + (f" · CP QC {vnd(qc)}{_pt(qc, k['dt'])}" if qc is not None else ""))
        dong.append(f"Tổng: <b>{vnd(dt_s)}</b> · GV {vnd(gv_s)} · phí sàn {vnd(phi_s)} · CP QC {vnd(qc_s)}")
        uoc = [k for k in san if k.get("don_uoc")]
        if uoc:
            dong.append("<i>Phí sàn ước tính cho đơn chưa quyết toán (" + "; ".join(
                f"{e(k['kenh'])} {k['don_uoc']}/{k['don']} đơn × {k.get('ty_le_phi', 0):.1%}".replace(".", ",") for k in uoc)
                + " — Shopee: tỉ lệ phí thật của đơn đã quyết toán; TikTok: phí / doanh thu sao kê TikTok 30 ngày)</i>")

    dt, gv, qc = dt_nv + dt_bl + dt_s, gv_nv + gv_bl + gv_s, chi + qc_s
    lai = dt - gv - phi_s - qc
    dong += ["", "💰 <b>Tổng các kênh</b>",
             f"Doanh thu: <b>{vnd(dt)}</b>",
             f"− Giá vốn: {vnd(gv)}{_pt(gv, dt)}",
             f"− Phí sàn: {vnd(phi_s)}{_pt(phi_s, dt)}",
             f"− CP QC (FB + sàn): {vnd(qc)}{_pt(qc, dt)}",
             f"= <b>Lãi sau GV, phí sàn, QC: {vnd(lai)}</b>{_pt(lai, dt)}",
             "<i>Chưa trừ ship, lương, mặt bằng, vận hành. GV đơn hàng = giá vốn bình quân trong đơn; GV bán lẻ = "
             "giá vốn bình quân hiện tại; phí sàn = tiền hàng − tiền sàn trả shop (đơn chưa quyết toán: ước tính).</i>"]
    if cp_san:
        dong.append(f"<i>CP QC sàn cập nhật {cp_san['luc']}" + (" — " + "; ".join(cp_san["thieu"]) if cp_san["thieu"] else "")
                    + "</i>")
    elif san:
        dong.append("<i>Chưa có số CP QC sàn — phần lãi chưa trừ QC Shopee/TikTok.</i>")
    return "\n".join(dong)


def _dong_ban_le(ban_le: list[dict]) -> list[str]:
    e = html.escape
    dong = [f"• {e(a['ten'])}: <b>{vnd(a['dt'])}</b> · {a['don']} HĐ" + (f" (trả {a['tra']})" if a["tra"] else "")
            + f" · {a['sp']:.0f} SP" for a in ban_le]
    if len(ban_le) > 1:
        dong.append(f"Tổng: <b>{vnd(sum(a['dt'] for a in ban_le))}</b> · {sum(a['don'] for a in ban_le)} HĐ")
    return dong


def soan_nhan_vien(nvien: list[dict], nhan: str, ban_le: list[dict] | None = None,
                   san: list[dict] | None = None) -> str:
    """Chỉ phần doanh thu Nhanh.vn theo nhân viên + bán lẻ cửa hàng (lệnh bot /doanhthuthangtruoc, /nhanvien)."""
    e = html.escape
    dong = [f"🧾 <b>Doanh thu Nhanh.vn theo nhân viên — {e(nhan)}</b>"]
    if not nvien and not ban_le:
        return dong[0] + "\nKhông có đơn nào."
    for a in nvien:
        dong.append(f"• {e(a['ten'])}: <b>{vnd(a['dt'])}</b> · {a['don']} đơn · {a['sp']:.0f} SP")
    dong.append(f"Tổng: <b>{vnd(sum(a['dt'] for a in nvien))}</b> · {sum(a['don'] for a in nvien)} đơn · "
                f"{sum(a['sp'] for a in nvien):.0f} SP")
    dong.append("Tính theo người tạo đơn, bỏ đơn huỷ · doanh thu = Tổng thu + Tiền chuyển khoản")
    if ban_le:
        dong += ["", "<b>Bán lẻ tại cửa hàng</b> (theo người lập phiếu)"] + _dong_ban_le(ban_le)
        dong.append("Doanh thu + VAT = Tổng bán − Chiết khấu − Tổng trả (như báo cáo Bán lẻ › Theo nhân viên)")
    if san:
        dong += ["", "<b>Doanh thu sàn Nhanh.vn</b>"] + _dong_san(san)
    dong += _dong_tong(nvien, ban_le, san)
    return "\n".join(dong)


def chia_tin(text: str, gioi_han: int = 3900) -> list[str]:
    """Cắt tin dài thành nhiều tin ở chỗ xuống dòng (Telegram tối đa 4096 ký tự).

    Không cắt giữa dòng: cắt ngang thẻ <b>/<a> thì Telegram từ chối cả tin ("can't parse entities") —
    03/10/2026 báo cáo đề xuất nhân nhóm dài ~4.200 ký tự bị mất cả hai phần vì vậy.
    """
    phan, cur = [], ""
    for dong in text.split("\n"):
        while len(dong) > gioi_han:  # 1 dòng quá dài (hiếm) — cắt cứng
            if cur:
                phan.append(cur)
                cur = ""
            phan.append(dong[:gioi_han])
            dong = dong[gioi_han:]
        if cur and len(cur) + 1 + len(dong) > gioi_han:
            phan.append(cur)
            cur = dong
        else:
            cur = f"{cur}\n{dong}" if cur else dong
    if cur:
        phan.append(cur)
    return phan


def gui(text: str) -> int | None:
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        raise SystemExit("Thiếu TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID trong config/.env.")
    mid = None
    for i, phan in enumerate(chia_tin(text)):
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=30, data={
            "chat_id": chat, "text": phan, "parse_mode": "HTML", "disable_web_page_preview": True})
        if not r.json().get("ok"):
            raise SystemExit(f"Telegram lỗi: {r.text[:300]}")
        if i == 0:
            mid = r.json()["result"]["message_id"]
    return mid


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ngay", default="hom-qua", help="hom-qua | hom-nay | thang-nay | <số ngày qua>")
    ap.add_argument("--top", type=int, default=0, help="liệt kê N chiến dịch chi nhiều nhất (mặc định không)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    global TOP
    TOP = a.top
    tu, den, nhan = khoang_ngay(a.ngay)
    nh = so_lieu_nhanh(tu, den)
    tin = soan_tin(lay_so_lieu(tu, den), nhan, nh["nv"], nh["san"], nh["ban_le"], cp_qc_san(tu, den))
    if a.dry_run:
        print(tin)
    else:
        gui(tin)
        print("Đã gửi Telegram.")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as e:  # traceback mặc định in URL kèm access_token vào log
        raise SystemExit(f"Lỗi mạng: {fb.an_bi_mat(e)}")
