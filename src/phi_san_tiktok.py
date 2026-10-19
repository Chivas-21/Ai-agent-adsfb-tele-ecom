"""Phí sàn TikTok thật theo sao kê (Seller Center → Tài chính → Báo cáo) — cho /baocaotaichinh.

Chủ trang (16/10/2026): "phí sàn TIKTOK sao ít thế này" — báo cáo ghi 3,6% vì từ ~26/09/2026 Nhanh không còn cập nhật
tiền TikTok quyết toán thật vào đơn (payment.businessPayment đứng ở ~96,5% tiền hàng, kể cả đơn đã giao 3 tuần), trong
khi sao kê TikTok 09–17/10 có phí 53,7tr / doanh thu 214,8tr = 25,0%. Shopee không bị (đơn đã quyết toán ~31,5%).

Mỗi sao kê ngày có doanh thu (earning), phí (fee, số âm) và điều chỉnh (adjust). Claude lấy qua Chrome cùng lượt
CP QC sàn (src/cp_qc_san_js/tiktok_sao_ke.js, API nội bộ /api/v1/pay/statement/list/detail) → data/phi_san_tiktok.json
{"ngay": {YYYY-MM-DD: {"dt": đ, "phi": đ (dương), "dc": đ}}, "luc": ts}. bao_cao_ads_telegram.ty_le_phi("TikTok Shop")
dùng ty_le() = Σ phí / Σ doanh thu sao kê 30 ngày gần nhất. Điều chỉnh (vd −21,2tr ngày 10/10) không tính vào phí.

    python src/phi_san_tiktok.py --can                    # {"tu": YYYY-MM-DD} — lấy sao kê từ ngày này tới nay
    python src/phi_san_tiktok.py --luu "10-17:31229470:7681710:0;…"
    python src/phi_san_tiktok.py --ty-le
"""
import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "data" / "phi_san_tiktok.json"
SO_NGAY = 30            # tỉ lệ phí = sao kê 30 ngày gần nhất
DT_TOI_THIEU = 20e6     # ít doanh thu hơn thì không đủ tin → dùng tỉ lệ cũ
LAY_LAI = 3             # luôn lấy lại 3 ngày sao kê gần nhất (sao kê mới sinh hằng ngày)


def _doc() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ngay": {}}


def can_lay() -> dict:
    """Ngày sao kê sớm nhất cần lấy: lần đầu 45 ngày, sau đó từ ngày mới nhất đã có − LAY_LAI."""
    d = _doc()["ngay"]
    tu = (date.fromisoformat(max(d)) - timedelta(days=LAY_LAI)) if d else date.today() - timedelta(days=45)
    return {"tu": tu.isoformat()}


def _ngay_gon(md: str) -> str:
    """'09-30' → '2026-09-30'; tháng lớn hơn tháng hiện tại → năm trước (sao kê có thể ghi ngày mai → không lùi năm)."""
    h = date.today() + timedelta(days=2)
    m = int(md[:2])
    return f"{h.year - (m > h.month)}-{md}"


def luu(chuoi: str) -> str:
    """Chuỗi gọn từ Chrome 'MM-DD:doanh thu:phí:điều chỉnh;…' (phí dương; nhiều sao kê cùng ngày đã cộng sẵn)."""
    d = _doc()
    n = 0
    for phan in filter(None, chuoi.split(";")):
        x = phan.split(":")
        d["ngay"][_ngay_gon(x[0])] = {"dt": round(float(x[1])), "phi": round(abs(float(x[2]))), "dc": round(float(x[3]))}
        n += 1
    d["luc"] = time.time()
    tam = FILE.with_suffix(".tmp")
    tam.write_text(json.dumps(d, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tam.replace(FILE)
    r = ty_le()
    return f"Sao kê TikTok: {n} ngày" + (f" · tỉ lệ phí 30 ngày {r:.1%}" if r else "")


def ty_le(den: str | None = None) -> float | None:
    """Σ phí / Σ doanh thu sao kê trong SO_NGAY ngày tới `den` (mặc định hôm nay); None nếu chưa đủ số liệu."""
    d1 = date.fromisoformat(den) if den else date.today()
    d0 = d1 - timedelta(days=SO_NGAY)
    ds = [v for n, v in _doc()["ngay"].items() if d0.isoformat() < n <= (d1 + timedelta(days=2)).isoformat()]
    dt = sum(v["dt"] for v in ds)
    return round(sum(v["phi"] for v in ds) / dt, 4) if dt >= DT_TOI_THIEU else None


def luc_cap_nhat() -> str:
    t = _doc().get("luc")
    return datetime.fromtimestamp(t).strftime("%H:%M %d/%m") if t else ""


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--can", action="store_true")
    ap.add_argument("--luu", help="chuỗi gọn 'MM-DD:dt:phi:dc;…'")
    ap.add_argument("--ty-le", action="store_true")
    a = ap.parse_args()
    if a.can:
        print(json.dumps(can_lay()))
    elif a.luu:
        print(luu(a.luu))
    elif a.ty_le:
        print(ty_le())


if __name__ == "__main__":
    main()
