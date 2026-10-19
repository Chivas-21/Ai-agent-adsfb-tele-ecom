"""Top 10 sản phẩm cha theo kênh — 3 nhân viên online, Shopee, TikTok Shop, cửa hàng bán lẻ — số lượng, doanh thu,
tồn có thể bán ở kho tổng.

Chủ trang (06/10/2026): "Top 10 sản phẩm cha, kèm số lượng và doanh thu của Doanh thu Nhanh.vn theo nhân viên"
→ chốt: 1 bảng top 10 xếp theo TỔNG của 3 nhân viên (NHAN_VIEN_BAO_CAO), không chia từng người, kèm số lượng tồn
CÓ THỂ BÁN ở kho tổng "Lamme Việt Nam" (depot 227527) lúc gõ lệnh; gộp sản phẩm tên gần giống (A27 / A27.1, combo);
sau đó thêm kênh Shopee, TikTok Shop, cửa hàng bán lẻ.
- 3 nhân viên: đơn tạo trong kỳ theo người tạo đơn, bỏ huỷ; tổng = Tổng thu + chuyển khoản (khớp /nhanvien).
- Sàn (saleChannel 42/50 Shopee, 48 TikTok Shop): bỏ huỷ, bỏ đơn trạng thái hoàn và chính đơn loại 14/16/17; trừ hàng
  khách trả sau khi giao (đơn loại 14/16 trỏ về đơn gốc trong kỳ) — tổng khớp /san.
- Cửa hàng: hoá đơn bán lẻ (bill/retail) của CUA_HANG_BAO_CAO, phiếu bán (type 2) − phiếu khách trả (type 1, related 6);
  tổng = Σ payment.amount (khớp phần bán lẻ trong báo cáo); hoá đơn không có mã cha → tra product/list {ids}.
- Sản phẩm: gộp theo parentCode/parentName; doanh thu = tiền hàng sau giảm giá (đơn: totalAmount, không gồm ship;
  hoá đơn: amount từng dòng, chưa trừ chiết khấu cả hoá đơn).
- Tồn: product/list {ids: [1 mã con đã bán]} → parentId → product/list {parentId} → product/inventory {ids} →
  Σ available ở KHO_TONG; combo là mã ảo nên không cộng tồn.

Bot: /topsp (tháng này) | thangtruoc | 7ngay (7 ngày qua, không gồm hôm nay) | homnay | homqua. Số bán của kỳ đã kết thúc lưu 6 giờ (data/top_sp_cache_v4.json);
tồn kho luôn lấy mới.

    python src/top_sp_nhan_vien.py [từ YYYY-MM-DD] [đến YYYY-MM-DD]   (mặc định: từ đầu tháng tới hôm nay)
"""
import html
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from bao_cao_ads_telegram import CUA_HANG_BAO_CAO, KENH_SAN, LOAI_DON_HOAN, NHAN_VIEN_BAO_CAO, vnd
from constants import DEPOTS, STATUS_GROUP
from nhanh_client import VN_TZ, NhanhClient

TOP = 10
KHO_TONG = int(__import__("cau_hinh").lay("nhanh.kho_tong") or 0)   # kho tổng (config/doanh_nghiep.yaml → nhanh.kho_tong)
CACHE = Path(__file__).resolve().parent.parent / "data" / "top_sp_cache_v4.json"   # v4: thêm sàn + cửa hàng
KENH = [("nv", "👩‍💼", "3 nhân viên online"), ("Shopee", "🛍", "Shopee"), ("TikTok Shop", "🎵", "TikTok Shop"),
        ("cua_hang", "🏬", "Cửa hàng bán lẻ (HN + HCM)")]
HIEN = [("tong", "💰", "Tổng các kênh")] + KENH   # thứ tự hiển thị: bảng tổng các kênh đứng đầu


def _nhom() -> dict:
    return {"don": 0, "dt": 0.0, "sl": 0, "sp": {}}


def _cong_sp(g: dict, ma: str, ten: str, sl: float, dt: float, pid) -> None:
    sp = g["sp"].setdefault(ma, {"ten": ten, "sl": 0, "dt": 0.0, "pid": pid})
    sp["sl"] += sl
    sp["dt"] += dt
    g["sl"] += sl


def _ma_ten(p: dict) -> tuple[str, str]:
    ma = (p.get("parentCode") or p.get("code") or "?").strip()
    return ma, (p.get("parentName") or p.get("name") or ma).strip()


def theo_san_pham(tu: str, den: str) -> dict:
    """{kênh: {"don", "dt", "sl", "sp": {mã cha: {"ten", "sl", "dt", "pid"}}}} — kênh = nv | Shopee | TikTok Shop | cua_hang."""
    t0 = datetime.fromisoformat(tu).replace(tzinfo=VN_TZ)
    t1 = min(datetime.fromisoformat(den).replace(tzinfo=VN_TZ) + timedelta(days=1), datetime.now(VN_TZ))
    chon = {t.casefold() for t in NHAN_VIEN_BAO_CAO}
    kq = {k: _nhom() for k, _, _ in KENH}
    goc_san: dict[int, str] = {}
    c = NhanhClient()
    for o in c.list_orders(t0, t1):
        i = o["info"]
        g = STATUS_GROUP.get(i["status"])
        if g == "cancelled":
            continue
        kenh = KENH_SAN.get((o.get("channel") or {}).get("saleChannel"))
        if kenh and g != "returned" and i.get("type") not in (*LOAI_DON_HOAN, 17):
            s = kq[kenh]
            s["don"] += 1
            for p in o.get("products") or []:
                s["dt"] += p.get("totalAmount") or 0
                _cong_sp(s, *_ma_ten(p), p.get("quantity") or 0, p.get("totalAmount") or 0, p.get("productId"))
            goc_san[i["id"]] = kenh
        ten = (i.get("createdByName") or "").strip() or (i.get("saleName") if i.get("createdById") and
                                                        i.get("createdById") == i.get("saleId") else "")
        if not i.get("createdById") or ten.casefold() not in chon:
            continue
        nv, pay = kq["nv"], o.get("payment") or {}
        nv["don"] += 1
        nv["dt"] += (pay.get("codAmount") or 0) + (pay.get("transfer") or {}).get("amount", 0)
        for p in o.get("products") or []:
            _cong_sp(nv, *_ma_ten(p), p.get("quantity") or 0, p.get("totalAmount") or 0, p.get("productId"))
    # Sàn: trừ hàng khách trả sau khi đã giao (đơn loại 14/16 tạo từ đầu kỳ tới nay, trỏ về đơn gốc ở trên)
    bay_gio = datetime.now(VN_TZ)
    for loai in LOAI_DON_HOAN:
        dau = t0
        while dau < bay_gio:
            cuoi = min(dau + timedelta(days=30), bay_gio)
            for o in c.paginate("order/list", {"createdAtFrom": int(dau.timestamp()), "createdAtTo": int(cuoi.timestamp()),
                                               "type": loai, "saleChannels": sorted(KENH_SAN)}, size=100):
                i = o["info"]
                kenh = goc_san.get(i.get("originalOrderId"))
                if not kenh or STATUS_GROUP.get(i["status"]) == "cancelled":
                    continue
                for p in o.get("products") or []:
                    kq[kenh]["dt"] -= p.get("totalAmount") or 0
                    _cong_sp(kq[kenh], *_ma_ten(p), -(p.get("quantity") or 0), -(p.get("totalAmount") or 0),
                             p.get("productId"))
            dau = cuoi
    _cua_hang(c, tu, den, kq["cua_hang"])
    return kq


def _cua_hang(c: NhanhClient, tu: str, den: str, g: dict) -> None:
    """Hoá đơn bán lẻ của 2 cửa hàng → g; mã cha tra qua product/list vì hoá đơn chỉ có mã con."""
    chon = {t.casefold() for t in CUA_HANG_BAO_CAO}
    d0, d1 = date.fromisoformat(tu), min(date.fromisoformat(den), date.today())
    dong: list[tuple[int, str, str, float, float]] = []   # (id mã con, mã, tên, sl, tiền) — dấu âm = khách trả
    while d0 <= d1:
        cuoi = min(d0 + timedelta(days=30), d1)
        for b in c.paginate("bill/retail", {"fromDate": d0.isoformat(), "toDate": cuoi.isoformat()}):
            if ((b.get("created") or {}).get("name") or "").strip().casefold() not in chon:
                continue
            if b.get("type") == 2:
                dau = 1
            elif b.get("type") == 1 and (b.get("related") or {}).get("type") == 6:
                dau = -1
            else:
                continue
            g["don"] += dau == 1
            g["dt"] += dau * ((b.get("payment") or {}).get("amount") or 0)
            for p in b.get("products") or []:
                dong.append((p.get("id"), p.get("code") or "?", p.get("name") or "?",
                             dau * (p.get("quantity") or 0), dau * (p.get("amount") or 0)))
        d0 = cuoi + timedelta(days=1)
    ids = sorted({x[0] for x in dong if x[0]})
    cha_cua: dict[int, int] = {}
    for k in range(0, len(ids), 100):
        for p in c.call("product/list", {"filters": {"ids": ids[k:k + 100]}, "paginator": {"size": 100}}).get("data") or []:
            cha_cua[p["id"]] = p.get("parentId") or 0
    cha_ids = sorted({v for v in cha_cua.values() if v > 0})
    cha: dict[int, tuple[str, str]] = {}
    for k in range(0, len(cha_ids), 100):
        for p in c.call("product/list", {"filters": {"ids": cha_ids[k:k + 100]}, "paginator": {"size": 100}}).get("data") or []:
            cha[p["id"]] = (p.get("code") or "?", p.get("name") or "?")
    for pid, ma, ten, sl, tien in dong:
        ma, ten = cha.get(cha_cua.get(pid, 0), (ma, ten))
        _cong_sp(g, ma.strip(), ten.strip(), sl, tien, pid)


def theo_san_pham_cache(tu: str, den: str, gio: float = 6) -> dict:
    if den >= date.today().isoformat():
        return theo_san_pham(tu, den)
    try:
        kho = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kho = {}
    khoa = f"{tu}_{den}"
    if khoa in kho and time.time() - kho[khoa]["luc"] < gio * 3600:
        return kho[khoa]["kq"]
    kq = theo_san_pham(tu, den)
    kho[khoa] = {"luc": time.time(), "kq": kq}
    CACHE.write_text(json.dumps(kho, ensure_ascii=False), encoding="utf-8")
    return kq


def ton_kho_tong(pids: dict[str, int]) -> dict[str, float]:
    """{mã cha: Σ tồn có thể bán ở KHO_TONG của mọi mã con}; pids = {mã cha: 1 mã con đã bán}."""
    c = NhanhClient()
    ids = sorted({i for i in pids.values() if i})
    cha: dict[int, int] = {}
    for k in range(0, len(ids), 100):
        for p in c.call("product/list", {"filters": {"ids": ids[k:k + 100]}, "paginator": {"size": 100}}).get("data") or []:
            cha[p["id"]] = p.get("parentId")
    con: dict[str, list[int]] = {}
    con_cua_cha: dict[int, list[int]] = {}
    for ma, pid in pids.items():
        par = cha.get(pid)
        if par and par > 0:   # có sản phẩm cha → lấy mọi mã con của cha (1 lần / cha)
            if par not in con_cua_cha:
                con_cua_cha[par] = [p["id"] for p in c.paginate("product/list", {"parentId": par}, size=100)]
            con[ma] = con_cua_cha[par]
        elif pid:             # sản phẩm độc lập
            con[ma] = [pid]
    tat = sorted({i for ds in con.values() for i in ds})
    ton: dict[int, float] = {}
    for k in range(0, len(tat), 100):
        for x in c.call("product/inventory", {"filters": {"ids": tat[k:k + 100]},
                                              "paginator": {"size": 100}}).get("data") or []:
            d = next((d for d in (x.get("inventory") or {}).get("depots") or [] if d.get("id") == KHO_TONG), {})
            ton[x["productId"]] = d.get("available") or 0
    return {ma: sum(ton.get(i, 0) for i in ds) for ma, ds in con.items()}


# Gộp sản phẩm cha tên gần giống (chủ trang 06/10/2026: "A27 vs A27.1; A2 vs A2 combo"):
# - combo: mã "<mã gốc>-COMBO2-…", tên "[Combo] <tên gốc> - 2 Chiếc Mix - …" → về mã/tên gốc;
# - cùng mã mẫu trong tên, bỏ đuôi phiên bản: A27 / A27.1, QL01 / QL01.3, QL02 / QL02.1 / QL02.3, VL106…
_MA_MAU = re.compile(r"(?<![\w.])((?:QL|VL|ALT|AL|A|E)\d+)((?:\.\d+)?)(?![\w.])")


def _la_combo(ma: str) -> bool:
    return "-COMBO" in ma.upper()


def _ten_goc(ten: str) -> str:
    """'[Combo] Áo lót - A2 - 2 Chiếc Mix - Ghi - L + Đen - L' → 'Áo lót - A2'."""
    ten = re.sub(r"^\[combo\]\s*", "", ten.strip(), flags=re.I)
    return re.split(r"\s+-\s+\d+\s+Chiếc\s+Mix\b", ten, maxsplit=1, flags=re.I)[0].strip()


def gop_ten_gan_giong(sp: dict) -> dict:
    """{khoá: {"ten", "sl", "dt", "ma": [mã cha], "gom": [nhãn hiển thị]}} — gộp combo + cùng mã mẫu."""
    nhom: dict[str, dict] = {}
    for ma, s in sp.items():
        ten = _ten_goc(s["ten"])
        m = _MA_MAU.search(ten)
        khoa = f"mau:{m.group(1)}" if m else f"ma:{re.split('-combo', ma, maxsplit=1, flags=re.I)[0]}"
        g = nhom.setdefault(khoa, {"ten": "", "sl": 0, "dt": 0.0, "ma": [], "gom": [], "_ten_dt": -1.0})
        g["sl"] += s["sl"]
        g["dt"] += s["dt"]
        g["ma"].append(ma)
        nhan = ("combo " if _la_combo(ma) else "") + (m.group(1) + m.group(2) if m else "")
        nhan = nhan.strip() or ("combo" if _la_combo(ma) else "mã gốc")
        if nhan not in g["gom"]:
            g["gom"].append(nhan)
        # tên hiển thị: mã thường bán nhiều nhất (combo chỉ dùng khi nhóm toàn combo)
        diem = s["dt"] + (0 if _la_combo(ma) else 1e15)
        if diem > g["_ten_dt"]:
            g["ten"], g["_ten_dt"] = ten, diem
    return nhom


def du_lieu(kq: dict, top: int = TOP) -> dict:
    """{"kenh": [{"k", "bieu", "ten", "dt", "don", "dv", "sl", "dong": [{"ten", "gom", "combo", "sl", "dt", "ton"}]}],
    "ton_loi": bool, "luc": "HH:MM"} — dùng chung cho tin chữ và ảnh bảng."""
    if "nv" not in kq:   # cache cũ (chỉ 3 nhân viên)
        kq = {"nv": kq if "sp" in kq else _nhom()}
    # Tổng các kênh (chủ trang thêm 06/10/2026): cộng số bán từng mã cha của 4 kênh; tổng = Σ tổng 4 kênh
    # (= "Tổng doanh thu các kênh" của báo cáo ngày).
    tong = _nhom()
    for k, _, _ in KENH:
        g = kq.get(k) or _nhom()
        tong["don"] += g["don"]
        tong["dt"] += g["dt"]
        tong["sl"] += g["sl"]
        for ma, s in g["sp"].items():
            t = tong["sp"].setdefault(ma, {"ten": s["ten"], "sl": 0, "dt": 0.0, "pid": s.get("pid")})
            t["sl"] += s["sl"]
            t["dt"] += s["dt"]
    kq = {**kq, "tong": tong}
    bang = {}
    for k, _, _ in HIEN:
        g = kq.get(k) or _nhom()
        bang[k] = sorted((x | {"khoa": kh} for kh, x in gop_ten_gan_giong(g["sp"]).items() if x["sl"] > 0 or x["dt"] > 0),
                         key=lambda x: -x["dt"])[:top]
    # Tồn theo NHÓM CHUNG mọi kênh (A27.1 ở TikTok cũng cộng tồn A27 dù TikTok không bán A27);
    # chỉ cộng mã thường — combo là mã ảo ghép từ mã thường, cộng vào sẽ tính trùng.
    tat_sp = {ma: s for k, _, _ in KENH for ma, s in (kq.get(k) or _nhom())["sp"].items()}
    nhom_chung = gop_ten_gan_giong(tat_sp)
    can = {x["khoa"] for k, _, _ in HIEN for x in bang[k]}
    try:
        ton_ma = ton_kho_tong({ma: tat_sp[ma].get("pid") for kh in can for ma in nhom_chung[kh]["ma"]
                               if not _la_combo(ma)})
        ton = {kh: sum(ton_ma.get(ma, 0) for ma in nhom_chung[kh]["ma"] if not _la_combo(ma)) for kh in can
               if any(not _la_combo(ma) for ma in nhom_chung[kh]["ma"])}
    except Exception as ex:  # noqa: BLE001 — lỗi tồn kho không chặn phần doanh số
        print(f"lỗi lấy tồn kho: {ex}", file=sys.stderr)
        ton = None
    ra = []
    for k, bieu, ten_kenh in HIEN:
        g = kq.get(k) or _nhom()
        ra.append({"k": k, "bieu": bieu, "ten": ten_kenh, "dt": g["dt"], "don": g["don"], "sl": g["sl"],
                   "dv": {"cua_hang": "HĐ", "tong": "đơn + HĐ"}.get(k, "đơn"),
                   "dong": [{"ten": x["ten"], "gom": x["gom"] if len(x["gom"]) > 1 else [],
                             "combo": all(_la_combo(ma) for ma in x["ma"]), "sl": x["sl"], "dt": x["dt"],
                             "ton": ton.get(x["khoa"]) if ton is not None else None} for x in bang[k]]})
    return {"kenh": ra, "ton_loi": ton is None, "luc": f"{datetime.now(VN_TZ):%H:%M}"}


GHI_CHU = ("Tồn = có thể bán ở kho tổng {kho} lúc {luc}. Doanh thu sản phẩm = tiền hàng sau giảm giá (không gồm ship). "
           "NV: đơn theo người tạo, bỏ huỷ; sàn: bỏ huỷ + hoàn (trừ cả hàng trả sau giao); cửa hàng: bán − khách trả.")


def soan_tin(kq: dict, nhan: str, top: int = TOP, d: dict | None = None) -> str:
    e = html.escape
    d = d or du_lieu(kq, top)
    dong = [f"🏆 <b>Top {top} sản phẩm cha theo kênh — {e(nhan)}</b>"]
    for c in d["kenh"]:
        dong += ["", f"{c['bieu']} <b>{c['ten']}: {vnd(c['dt'])}</b> · {c['don']} {c['dv']} · {c['sl']:.0f} SP"]
        if not c["dong"]:
            dong.append("  Chưa có bán.")
        for n, x in enumerate(c["dong"], 1):
            dong.append(f"{n}. {e(x['ten'])}" + (" <i>(combo)</i>" if x["combo"] else "")
                        + (f" <i>(gộp {e(', '.join(x['gom']))})</i>" if x["gom"] else "")
                        + f": <b>{x['sl']:.0f}</b> SP · {vnd(x['dt'])}"
                        + (f" · tồn <b>{x['ton']:,.0f}</b>".replace(",", ".") if x["ton"] is not None else ""))
    dong += ["", "<i>" + e(GHI_CHU.format(kho=DEPOTS.get(KHO_TONG, KHO_TONG), luc=d["luc"])) + "</i>"]
    if d["ton_loi"]:
        dong.append("⚠️ Không lấy được tồn kho từ Nhanh lúc này.")
    return "\n".join(dong)


# ---------------------------------------------------------------- ảnh bảng (Telegram không hiển thị bảng HTML)
_FONT = "C:/Windows/Fonts/segoeui.ttf"
_FONT_DAM = "C:/Windows/Fonts/segoeuib.ttf"
MAU = {"nen": (255, 255, 255), "chu": (33, 37, 41), "mo": (108, 117, 125), "ke": (222, 226, 230),
       "chan": (246, 247, 249), "dau": (52, 58, 64)}
MAU_KENH = {"tong": (111, 66, 193), "nv": (13, 110, 253), "Shopee": (238, 77, 45), "TikTok Shop": (24, 24, 27), "cua_hang": (25, 135, 84)}
TEN_KENH_ANH = {"tong": "TỔNG CÁC KÊNH", "nv": "3 NHÂN VIÊN ONLINE", "Shopee": "SHOPEE", "TikTok Shop": "TIKTOK SHOP",
                "cua_hang": "CỬA HÀNG BÁN LẺ (HN + HCM)"}
COT = [("#", 50, "c"), ("Sản phẩm", 650, "l"), ("SL", 90, "r"), ("Doanh thu", 210, "r"), ("Tồn kho tổng", 180, "r")]


def ve_anh(nhan: str, d: dict, top: int = TOP) -> bytes:
    """Ảnh PNG: mỗi kênh 1 bảng # · Sản phẩm · SL · Doanh thu · Tồn kho tổng."""
    import io
    from PIL import Image, ImageDraw, ImageFont
    f = lambda c, dam=False: ImageFont.truetype(_FONT_DAM if dam else _FONT, c)  # noqa: E731
    F_TIEU, F_KENH, F_DAU, F_CHU, F_NHO = f(34, True), f(25, True), f(20, True), f(22), f(18)
    LE = 30
    W = LE * 2 + sum(r for _, r, _ in COT)
    H_DONG, H_DAU, H_KENH, H_GHI = 44, 40, 54, 26
    nhap = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    ghi = GHI_CHU.format(kho=DEPOTS.get(KHO_TONG, KHO_TONG), luc=d["luc"])
    dong_ghi, hien = [], ""
    for tu in ghi.split():   # ghi chú xuống dòng theo bề rộng ảnh
        if hien and nhap.textlength(hien + " " + tu, font=F_NHO) > W - 2 * LE:
            dong_ghi.append(hien)
            hien = tu
        else:
            hien = (hien + " " + tu).strip()
    dong_ghi.append(hien)
    so_dong = sum(max(len(c["dong"]), 1) for c in d["kenh"])
    H = 120 + len(d["kenh"]) * (H_KENH + H_DAU + 24) + so_dong * H_DONG + 10 + H_GHI * len(dong_ghi) + 16
    img = Image.new("RGB", (W, H), MAU["nen"])
    ve = ImageDraw.Draw(img)

    def chu(x, y, s, font, mau=MAU["chu"], canh="l", rong=0):
        w = ve.textlength(s, font=font)
        x = x + rong - w if canh == "r" else x + (rong - w) / 2 if canh == "c" else x
        ve.text((x, y), s, font=font, fill=mau)

    def cat(s, font, rong):
        if ve.textlength(s, font=font) <= rong:
            return s
        while s and ve.textlength(s + "…", font=font) > rong:
            s = s[:-1]
        return s.rstrip() + "…"

    so = lambda x: f"{x:,.0f}".replace(",", ".")  # noqa: E731
    chu(LE, 24, f"Top {top} sản phẩm cha theo kênh", F_TIEU)
    chu(LE, 72, nhan, F_CHU, MAU["mo"])
    y = 120
    for c in d["kenh"]:
        ve.rectangle([LE, y, W - LE, y + H_KENH], fill=MAU_KENH.get(c["k"], MAU["dau"]))
        chu(LE + 16, y + 12, TEN_KENH_ANH.get(c["k"], c["ten"]), F_KENH, (255, 255, 255))
        chu(LE, y + 15, f"{vnd(c['dt'])} · {c['don']} {c['dv']} · {so(c['sl'])} SP", F_DAU, (255, 255, 255), "r",
            W - 2 * LE - 16)
        y += H_KENH
        ve.rectangle([LE, y, W - LE, y + H_DAU], fill=MAU["chan"])
        x = LE
        for ten_cot, rong, canh in COT:
            chu(x + 8, y + 9, ten_cot, F_DAU, MAU["mo"], canh, rong - 16)
            x += rong
        y += H_DAU
        if not c["dong"]:
            chu(LE + 58, y + 10, "Chưa có bán.", F_CHU, MAU["mo"])
            y += H_DONG
        for n, r in enumerate(c["dong"], 1):
            if n % 2 == 0:
                ve.rectangle([LE, y, W - LE, y + H_DONG], fill=MAU["chan"])
            ten = r["ten"] + (" (combo)" if r["combo"] else "")
            phu = f"  gộp {', '.join(r['gom'])}" if r["gom"] else ""
            gia_tri = [str(n), None, so(r["sl"]), vnd(r["dt"]), so(r["ton"]) if r["ton"] is not None else "—"]
            x = LE
            for (ten_cot, rong, canh), v in zip(COT, gia_tri):
                if v is None:   # cột sản phẩm: tên + "gộp …" chữ nhỏ màu nhạt
                    cho_phu = min(ve.textlength(phu, font=F_NHO), 230) if phu else 0
                    ten_cat = cat(ten, F_CHU, rong - 16 - cho_phu)
                    chu(x + 8, y + 9, ten_cat, F_CHU)
                    if phu:
                        chu(x + 8 + ve.textlength(ten_cat, font=F_CHU), y + 13,
                            cat(phu, F_NHO, rong - 16 - ve.textlength(ten_cat, font=F_CHU)), F_NHO, MAU["mo"])
                else:
                    chu(x + 8, y + 9, v, F_CHU, MAU["chu"], canh, rong - 16)
                x += rong
            ve.line([LE, y + H_DONG, W - LE, y + H_DONG], fill=MAU["ke"])
            y += H_DONG
        y += 24
    for k, s in enumerate(dong_ghi):
        ve.text((LE, y + 10 + H_GHI * k), s, font=F_NHO, fill=MAU["mo"])
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def bao_cao_anh(kq: dict, nhan: str, top: int = TOP) -> dict:
    """Cho bot: {"anh": PNG | None, "chu_thich": caption ngắn, "tin": bản chữ dự phòng}."""
    d = du_lieu(kq, top)
    tin = soan_tin(kq, nhan, top, d)
    try:
        anh = ve_anh(nhan, d, top)
    except Exception as ex:  # noqa: BLE001 — vẽ lỗi thì gửi bản chữ
        print(f"lỗi vẽ ảnh: {ex}", file=sys.stderr)
        anh = None
    chu_thich = f"🏆 Top {top} sản phẩm cha theo kênh — {html.escape(nhan)}" + (
        "\n⚠️ Không lấy được tồn kho từ Nhanh lúc này." if d["ton_loi"] else "")
    return {"anh": anh, "chu_thich": chu_thich, "tin": tin}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    h = date.today()
    ts = [a for a in sys.argv[1:] if not a.startswith("--")]
    tu = ts[0] if ts else h.replace(day=1).isoformat()
    den = ts[1] if len(ts) > 1 else h.isoformat()
    kq = theo_san_pham(tu, den)
    if "--anh" in sys.argv:   # lưu ảnh bảng ra data/top_sp.png để xem thử
        out = Path(__file__).resolve().parent.parent / "data" / "top_sp.png"
        out.write_bytes(ve_anh(f"{tu} → {den}", du_lieu(kq)))
        print(f"đã lưu {out}")
    else:
        print(re.sub(r"</?[bi]>", "", soan_tin(kq, f"{tu} → {den}")))


if __name__ == "__main__":
    main()
