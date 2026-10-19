"""Chi phí quảng cáo sàn (Shopee Ads, TikTok GMV Max) theo ngày — để báo cáo Telegram ghi CP QC + % doanh thu sàn.

Chủ trang (06/10/2026): "lấy chi phí của shopee và tiktok" → chi phí quảng cáo, hiện trong báo cáo ngày + /san.
Chưa có API chính thức (Shopee Open Platform / TikTok API for Business cần app được duyệt), nên lấy bằng API nội bộ
của trang người bán đang đăng nhập trên Chrome — Claude chạy theo lịch trong phiên (Claude in Chrome):
  - Shopee: src/cp_qc_san_js/shopee.js trong banhang.shopee.vn, mỗi shop 1 lần (đổi shop ở /portal/shop → "Chi tiết").
    Tổng/ngày = Σ chi phí chiến dịch homepage/query (product_homepage_v3, shop_homepage, live_stream_homepage, display)
    + chiến dịch GMS (report/get product_gms). Kiểm 01–05/10 LAMME SHOP: QC sản phẩm 15.780.597đ = đúng số trên trang.
  - TikTok: src/cp_qc_san_js/tiktok.js trong seller-vn.tiktok.com/ads-creation/dashboard: post_campaign_list (query_list
    ["cost"]) Product GMV Max (304/307, gmv_roi_mode 2) + LIVE GMV Max (305). Kiểm 29/09–06/10: 13.901.403đ so với
    13.893.670đ trên trang (lệch 0,06% do hôm nay đang chạy).
Kết quả lưu data/cp_qc_san.json: {"ngay": {YYYY-MM-DD: {"Shopee": {tên shop: đ}, "TikTok Shop": {"product": đ,
"live": đ}}}, "luc": {"Shopee": ts, "TikTok Shop": ts}}.

Cập nhật định kỳ: lịch CronCreate trong phiên Claude "Lên camp FB / báo cáo Telegram" 60 phút/lần (phút 45,
8h–23h — chủ trang chọn 06/10/2026), tự gia hạn 6 ngày/lần qua data/cp_qc_san_lich.json — chỉ chạy khi phiên
Claude + Chrome đang mở và còn đăng nhập Shopee / TikTok Seller; không chạy thì báo cáo ghi giờ cập nhật cũ.

    python src/cp_qc_san.py --can               # in JSON các ngày cần lấy (thiếu từ đầu tháng trước + 3 ngày gần nhất)
    python src/cp_qc_san.py --ghi kq.json       # gộp kết quả lấy từ Chrome vào data/cp_qc_san.json
    python src/cp_qc_san.py --tiktok "10-05:1120293:930231;…"          # hoặc dạng chuỗi gọn
    python src/cp_qc_san.py --shopee "LAMME SHOP" "10-05:2771421;…"
    python src/cp_qc_san.py --tong 2026-10-01 2026-10-05
"""
import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "data" / "cp_qc_san.json"
import cau_hinh  # noqa: E402

SHOP_SHOPEE = tuple(cau_hinh.lay("san.shopee_shops") or ())   # tên đúng như shop_info trả về (config/doanh_nghiep.yaml)
LAY_LAI = 3   # luôn lấy lại 3 ngày gần nhất (hôm nay + 2 ngày trước — sàn còn cập nhật chi phí muộn)


def _doc() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ngay": {}, "luc": {}}


LAY_LAI_SAU = 6 * 3600   # hôm qua / hôm kia: lấy lại nếu lần lấy trước đã quá 6 giờ (lịch chạy 60 phút/lần)
# Tạm dừng tự cập nhật (chủ trang thêm 06/10/2026): bot /offchiphisan ghi cờ, /onchiphisan xoá; lịch trong phiên
# Claude đọc `--can` — đang tạm dừng thì trả {"tam_dung": …} và lịch bỏ qua, không mở Chrome.
FILE_TAM_DUNG = FILE.with_name("cp_qc_san_tam_dung.json")


def tam_dung() -> dict | None:
    """{"luc": "HH:MM dd/mm", "ai": tên} nếu đang tạm dừng, không thì None."""
    try:
        return json.loads(FILE_TAM_DUNG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def dat_tam_dung(bat: bool, ai: str = "") -> None:
    if bat:
        FILE_TAM_DUNG.write_text(json.dumps({"luc": datetime.now().strftime("%H:%M %d/%m"), "ai": ai},
                                            ensure_ascii=False), encoding="utf-8")
    else:
        FILE_TAM_DUNG.unlink(missing_ok=True)


def can_lay() -> dict:
    """{"Shopee": {tên shop: [ngày]}, "TikTok Shop": [ngày]} — ngày thiếu từ đầu tháng trước tới hôm nay, hôm nay
    (lần nào cũng lấy), và 2 ngày trước nếu lần lấy gần nhất đã quá LAY_LAI_SAU."""
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


def ghi(kq: dict) -> str:
    """kq = {"Shopee": {"ten": tên shop, "ngay": {ngày: {"tong": đ, ...}}}} hoặc
    {"TikTok Shop": {"ngay": {ngày: {"product": đ, "live": đ}}}} (có thể cả hai)."""
    d = _doc()
    ra = []
    if kq.get("Shopee"):
        s = kq["Shopee"]
        for n, v in s["ngay"].items():
            d["ngay"].setdefault(n, {}).setdefault("Shopee", {})[s["ten"]] = round(v["tong"])
            d.setdefault("lay", {}).setdefault(n, {})[s["ten"]] = time.time()
        d["luc"]["Shopee"] = time.time()
        ra.append(f"Shopee/{s['ten']}: {len(s['ngay'])} ngày")
    if kq.get("TikTok Shop"):
        for n, v in kq["TikTok Shop"]["ngay"].items():
            d["ngay"].setdefault(n, {})["TikTok Shop"] = {"product": round(v["product"]), "live": round(v["live"])}
            d.setdefault("lay", {}).setdefault(n, {})["TikTok Shop"] = time.time()
        d["luc"]["TikTok Shop"] = time.time()
        ra.append(f"TikTok: {len(kq['TikTok Shop']['ngay'])} ngày")
    tam = FILE.with_suffix(".tmp")
    tam.write_text(json.dumps(d, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tam.replace(FILE)
    return ", ".join(ra) or "không có gì"


def _ngay_gon(md: str) -> str:
    """'09-30' → '2026-09-30' (tháng lớn hơn tháng hiện tại → năm trước)."""
    h = date.today()
    m = int(md[:2])
    return f"{h.year - (m > h.month)}-{md}"


def ghi_gon(san: str, chuoi: str, ten_shop: str = "") -> str:
    """Chuỗi gọn từ Chrome (đỡ dài kết quả javascript_tool): TikTok 'MM-DD:product:live;…', Shopee 'MM-DD:tổng;…'."""
    ngay = {}
    for phan in filter(None, chuoi.split(";")):
        x = phan.split(":")
        ngay[_ngay_gon(x[0])] = ({"product": float(x[1]), "live": float(x[2])} if san == "tiktok" else {"tong": float(x[1])})
    return ghi({"TikTok Shop": {"ngay": ngay}} if san == "tiktok" else {"Shopee": {"ten": ten_shop, "ngay": ngay}})


def tong(tu: str, den: str) -> dict:
    """{"Shopee": đ | None, "TikTok Shop": đ | None, "thieu": [ghi chú], "luc": "HH:MM dd/mm"} cho [tu, den]."""
    d = _doc()
    d0, d1 = date.fromisoformat(tu), min(date.fromisoformat(den), date.today())
    ngay = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    kq, thieu = {}, []
    for san in ("Shopee", "TikTok Shop"):
        co = [n for n in ngay if san in d["ngay"].get(n, {})]
        if not co:
            kq[san] = None
            continue
        kq[san] = sum(sum(d["ngay"][n][san].values()) for n in co)
        if len(co) < len(ngay):
            thieu.append(f"{san} thiếu {len(ngay) - len(co)} ngày")
        if san == "Shopee":
            thieu_shop = [s for s in SHOP_SHOPEE if any(s not in d["ngay"][n]["Shopee"] for n in co)]
            if thieu_shop:
                thieu.append("Shopee thiếu shop " + ", ".join(thieu_shop))
    luc = [d["luc"][s] for s in ("Shopee", "TikTok Shop") if d["luc"].get(s)]
    td = tam_dung()
    if td:
        thieu.append(f"đang tạm dừng tự cập nhật từ {td['luc']} (/onchiphisan để bật lại)")
    kq["thieu"] = thieu
    kq["luc"] = datetime.fromtimestamp(min(luc)).strftime("%H:%M %d/%m") if luc else ""
    return kq


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--can", action="store_true")
    ap.add_argument("--ghi")
    ap.add_argument("--tong", nargs=2)
    ap.add_argument("--tiktok", help="chuỗi gọn 'MM-DD:product:live;…'")
    ap.add_argument("--shopee", nargs=2, metavar=("TEN_SHOP", "CHUOI"), help="tên shop + chuỗi gọn 'MM-DD:tổng;…'")
    a = ap.parse_args()
    if a.tiktok:
        print(ghi_gon("tiktok", a.tiktok))
    elif a.shopee:
        print(ghi_gon("shopee", a.shopee[1], a.shopee[0]))
    elif a.can:
        td = tam_dung()
        print(json.dumps({"tam_dung": td} if td else can_lay(), ensure_ascii=False))
    elif a.ghi:
        print(ghi(json.loads(Path(a.ghi).read_text(encoding="utf-8"))))
    elif a.tong:
        print(json.dumps(tong(*a.tong), ensure_ascii=False))


if __name__ == "__main__":
    main()
