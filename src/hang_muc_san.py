"""Doanh thu sàn theo hạng mục (nguồn đơn) theo ngày — bảng "Doanh thu theo hạng mục" trong /san và file HTML tài chính.

Chủ trang (10/10/2026): "phân tích thêm 1 bảng doanh thu của từng hạng mục": Shopee = Thẻ sản phẩm / Live / Video /
Aff Shopee; TikTok = Doanh thu Live / Video / TTMS (= Thẻ sản phẩm). Nhanh.vn không có thông tin này, nên lấy bằng API
nội bộ trang người bán trên Chrome đã đăng nhập (Claude in Chrome, cùng lượt lịch CP QC sàn — xem src/cp_qc_san.py):
  - Shopee: src/hang_muc_san_js/shopee.js — Phân tích bán hàng → Nguồn doanh thu (mydata dashboard/traffic-sources,
    đơn đã xác nhận), từng shop. Thẻ SP + Live + Video + Affiliate = tổng doanh thu. Đầm bầu T9: 606,7tr.
  - TikTok: src/hang_muc_san_js/tiktok.js — Compass "Tổng quan" (insights unified/query us_overview_stats): GMV tổng
    (4024), LIVE (4029), Video (4037), Thẻ sản phẩm (4033). T9: 1.030tr = LIVE 609,7 + Video 310,6 + Thẻ SP 109,9.
Số của sàn là doanh thu đặt hàng (GMV, gồm đơn sau này huỷ/hoàn) — lệch với doanh thu Nhanh.vn (đơn thành công);
bảng dùng để xem TỶ TRỌNG từng hạng mục.

Lưu data/hang_muc_san.json: {"ngay": {YYYY-MM-DD: {"Shopee": {tên shop: {tong, the, live, video, aff}},
"TikTok Shop": {tong, live, video, the}}}, "luc": {nguồn: ts}, "lay": {ngày: {nguồn: ts}}}.

    python src/hang_muc_san.py --can                                   # ngày cần lấy (thiếu từ đầu tháng trước + gần đây)
    python src/hang_muc_san.py --shopee "LAMME SHOP" "10-05:tong:the:live:video:aff;…"
    python src/hang_muc_san.py --tiktok "10-05:tong:live:video:the;…"
    python src/hang_muc_san.py --tong 2026-10-01 2026-10-09
"""
import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from cp_qc_san import LAY_LAI, LAY_LAI_SAU, SHOP_SHOPEE, _ngay_gon

FILE = Path(__file__).resolve().parent.parent / "data" / "hang_muc_san.json"
HANG_MUC = {   # thứ tự hiện trong bảng: (khoá, tên)
    "Shopee": (("the", "Thẻ sản phẩm"), ("live", "Live"), ("video", "Video"), ("aff", "Affiliate")),
    "TikTok Shop": (("live", "Live"), ("video", "Video"), ("the", "Thẻ SP (TTMS)")),
}
TRUONG = {"Shopee": ("tong", "the", "live", "video", "aff"), "TikTok Shop": ("tong", "live", "video", "the")}


def _doc() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ngay": {}, "luc": {}, "lay": {}}


def can_lay() -> dict:
    """{"Shopee": {tên shop: [ngày]}, "TikTok Shop": [ngày]} — giống cp_qc_san.can_lay: ngày thiếu từ đầu tháng trước,
    hôm nay, và 2 ngày trước nếu lần lấy gần nhất đã quá 6 giờ (đơn còn được xác nhận muộn)."""
    h = date.today()
    d0 = (h.replace(day=1) - timedelta(days=1)).replace(day=1)
    ngay = [(d0 + timedelta(days=i)).isoformat() for i in range((h - d0).days + 1)]
    gan = set(ngay[-LAY_LAI:])
    doc = _doc()
    d, lay = doc["ngay"], doc.get("lay", {})

    def can(n: str, nguon: str, co: bool) -> bool:
        return (not co or n == h.isoformat()
                or (n in gan and time.time() - lay.get(n, {}).get(nguon, 0) > LAY_LAI_SAU))
    return {"Shopee": {s: [n for n in ngay if can(n, s, s in d.get(n, {}).get("Shopee", {}))] for s in SHOP_SHOPEE},
            "TikTok Shop": [n for n in ngay if can(n, "TikTok Shop", "TikTok Shop" in d.get(n, {}))]}


def ghi_gon(san: str, chuoi: str, ten_shop: str = "") -> str:
    """Chuỗi gọn từ Chrome: Shopee 'MM-DD:tong:the:live:video:aff;…', TikTok 'MM-DD:tong:live:video:the;…'."""
    if san == "shopee" and ten_shop not in SHOP_SHOPEE:
        raise SystemExit(f"Tên shop lạ: {ten_shop!r} (cần một trong {SHOP_SHOPEE})")
    khoa = "Shopee" if san == "shopee" else "TikTok Shop"
    nguon = ten_shop if san == "shopee" else khoa
    d = _doc()
    n_ngay = 0
    for phan in filter(None, chuoi.split(";")):
        x = phan.split(":")
        n = _ngay_gon(x[0])
        v = dict(zip(TRUONG[khoa], (round(float(s)) for s in x[1:])))
        if khoa == "Shopee":
            d["ngay"].setdefault(n, {}).setdefault("Shopee", {})[ten_shop] = v
        else:
            d["ngay"].setdefault(n, {})[khoa] = v
        d.setdefault("lay", {}).setdefault(n, {})[nguon] = time.time()
        n_ngay += 1
    d["luc"][khoa] = time.time()
    tam = FILE.with_suffix(".tmp")
    tam.write_text(json.dumps(d, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tam.replace(FILE)
    return f"{nguon}: {n_ngay} ngày"


def tong(tu: str, den: str) -> dict:
    """{"Shopee": {tong, the, live, video, aff} | None, "TikTok Shop": {...} | None, "thieu": [ghi chú],
    "luc": "HH:MM dd/mm"} cộng các ngày trong [tu, den] (Shopee cộng 2 shop)."""
    d = _doc()
    d0, d1 = date.fromisoformat(tu), min(date.fromisoformat(den), date.today())
    ngay = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    kq, thieu = {}, []
    for san in ("Shopee", "TikTok Shop"):
        co = [n for n in ngay if san in d["ngay"].get(n, {})]
        if not co:
            kq[san] = None
            continue
        c = dict.fromkeys(TRUONG[san], 0)
        for n in co:
            for v in (d["ngay"][n][san].values() if san == "Shopee" else [d["ngay"][n][san]]):
                for k in c:
                    c[k] += v.get(k, 0)
        kq[san] = c
        if len(co) < len(ngay):
            thieu.append(f"{san} thiếu {len(ngay) - len(co)} ngày")
        if san == "Shopee":
            thieu_shop = [s for s in SHOP_SHOPEE if any(s not in d["ngay"][n]["Shopee"] for n in co)]
            if thieu_shop:
                thieu.append("Shopee thiếu shop " + ", ".join(thieu_shop))
    luc = [d["luc"][s] for s in ("Shopee", "TikTok Shop") if d["luc"].get(s)]
    kq["thieu"] = thieu
    kq["luc"] = datetime.fromtimestamp(min(luc)).strftime("%H:%M %d/%m") if luc else ""
    return kq


def dong(kq: dict) -> list[tuple[str, list[tuple[str, float, float]], float]]:
    """kq = tong(...) → [(sàn, [(hạng mục, doanh thu, tỷ trọng)], tổng)] để /san và HTML cùng trình bày.
    TikTok còn phần lẻ ngoài 3 hạng mục (≥ 0,5% tổng) thì thêm dòng "Khác"."""
    ra = []
    for san, hm in HANG_MUC.items():
        v = kq.get(san)
        if not v or not v["tong"]:
            continue
        t = v["tong"]
        hang = [(ten, v[k], v[k] / t) for k, ten in hm]
        con = t - sum(x[1] for x in hang)
        if abs(con) >= 0.005 * t:
            hang.append(("Khác", con, con / t))
        ra.append((san, hang, t))
    return ra


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--can", action="store_true")
    ap.add_argument("--tong", nargs=2)
    ap.add_argument("--tiktok", help="chuỗi gọn 'MM-DD:tong:live:video:the;…'")
    ap.add_argument("--shopee", nargs=2, metavar=("TEN_SHOP", "CHUOI"), help="tên shop + 'MM-DD:tong:the:live:video:aff;…'")
    a = ap.parse_args()
    if a.tiktok:
        print(ghi_gon("tiktok", a.tiktok))
    elif a.shopee:
        print(ghi_gon("shopee", a.shopee[1], a.shopee[0]))
    elif a.can:
        print(json.dumps(can_lay(), ensure_ascii=False))
    elif a.tong:
        print(json.dumps(tong(*a.tong), ensure_ascii=False))


if __name__ == "__main__":
    main()
