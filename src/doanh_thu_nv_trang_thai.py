"""Doanh thu Nhanh theo trạng thái (hủy / hoàn / thành công / đang gửi): 3 nhân viên + sàn Shopee / TikTok Shop
+ bán lẻ tại cửa hàng, và tổng các kênh.
Dùng: python doanh_thu_nv_trang_thai.py [từ YYYY-MM-DD] [đến YYYY-MM-DD]  (mặc định: từ đầu tháng tới hôm nay)

- Nhân viên: theo người tạo đơn; tiền đơn = Tổng thu (codAmount) + chuyển khoản, giống báo cáo Telegram. Đơn hoàn Nhanh
  xoá Tổng thu về 0 → lấy tiền hàng sau giảm giá.
- Sàn (thêm 05/10/2026, chủ trang yêu cầu): đơn channel.saleChannel 42/50 Shopee, 48 TikTok Shop; tiền = Σ
  products.totalAmount (như /san). Đơn khách trả SAU khi giao thành công (đơn mới loại 14/16 trỏ về đơn gốc) → chuyển
  tiền từ "Thành công" sang "Hoàn" (loại 14 trả cả đơn thì chuyển luôn 1 đơn). Không đếm chính đơn loại 14/16/17.
- Bán lẻ cửa hàng (thêm 05/10/2026): hoá đơn bán lẻ (bill/retail) của Cửa hàng Hà Nội / Hồ Chí Minh — bán xong là
  xong, không có trạng thái: phiếu bán tính vào "Thành công", phiếu khách trả tính vào "Hoàn".
- Tổng các kênh = nhân viên + sàn + cửa hàng, cộng theo từng trạng thái."""
import json
import re
import sys
import time
from pathlib import Path
from datetime import date, datetime, timedelta

from bao_cao_ads_telegram import KENH_SAN, LOAI_DON_HOAN, NHAN_VIEN_BAO_CAO, doanh_thu_ban_le, vnd
from constants import STATUS_GROUP
from nhanh_client import VN_TZ, NhanhClient

NHOM = [("success", "Thành công"), ("in_flight", "Đang gửi"), ("returned", "Hoàn"), ("cancelled", "Hủy")]


def _rong() -> dict:
    return {"don": 0, "dt": 0.0, **{g: [0, 0.0] for g, _ in NHOM}, "khac": [0, 0.0]}


def _cong(a: dict, g: str, tien: float) -> None:
    a["don"] += 1
    a["dt"] += tien
    a[g][0] += 1
    a[g][1] += tien


def theo_trang_thai(tu: str, den: str) -> dict:
    """{"nv": {tên: số liệu}, "san": {kênh: số liệu}, "ban_le": {cửa hàng: số liệu}}."""
    t0 = datetime.fromisoformat(tu).replace(tzinfo=VN_TZ)
    t1 = min(datetime.fromisoformat(den).replace(tzinfo=VN_TZ) + timedelta(days=1), datetime.now(VN_TZ))
    chon = {t.casefold(): t for t in NHAN_VIEN_BAO_CAO}
    nv = {t: _rong() for t in NHAN_VIEN_BAO_CAO}
    san = {k: _rong() for k in dict.fromkeys(KENH_SAN.values())}
    goc_san: dict[int, str] = {}   # đơn sàn thành công trong kỳ → kênh, để chuyển phần hoàn sau giao
    client = NhanhClient()
    for o in client.list_orders(t0, t1):
        i = o["info"]
        g = STATUS_GROUP.get(i["status"], "khac")
        kenh = KENH_SAN.get((o.get("channel") or {}).get("saleChannel"))
        if kenh and i.get("type") not in (*LOAI_DON_HOAN, 17):
            _cong(san[kenh], g, sum(p.get("totalAmount") or 0 for p in o.get("products") or []))
            if g == "success":
                goc_san[i["id"]] = kenh
        ten = (i.get("createdByName") or "").strip() or (i.get("saleName") if i.get("createdById") and
                                                        i.get("createdById") == i.get("saleId") else "")
        if not i.get("createdById") or ten.casefold() not in chon:
            continue
        pay = o.get("payment") or {}
        tien = (pay.get("codAmount") or 0) + (pay.get("transfer") or {}).get("amount", 0)
        if g == "returned" and not tien:  # đơn hoàn Nhanh xoá Tổng thu về 0 → lấy tiền hàng sau giảm giá
            tien = sum(p.get("totalAmount") or 0 for p in o.get("products") or [])
        _cong(nv[chon[ten.casefold()]], g, tien)
    # Đơn sàn khách trả sau khi đã giao thành công: đơn loại 14/16 tạo từ đầu kỳ tới nay, trỏ về đơn gốc ở trên
    bay_gio = datetime.now(VN_TZ)
    for loai in LOAI_DON_HOAN:
        dau = t0
        while dau < bay_gio:
            cuoi = min(dau + timedelta(days=30), bay_gio)
            for o in client.paginate("order/list", {"createdAtFrom": int(dau.timestamp()), "createdAtTo": int(cuoi.timestamp()),
                                                    "type": loai, "saleChannels": sorted(KENH_SAN)}, size=100):
                i = o["info"]
                kenh = goc_san.get(i.get("originalOrderId"))
                if not kenh or STATUS_GROUP.get(i["status"]) == "cancelled":
                    continue
                tien = sum(p.get("totalAmount") or 0 for p in o.get("products") or [])
                a = san[kenh]
                a["success"][1] -= tien
                a["returned"][1] += tien
                if loai == 14:   # trả cả đơn → đơn gốc tính là đơn hoàn; loại 16 (một phần) chỉ chuyển tiền
                    a["success"][0] -= 1
                    a["returned"][0] += 1
            dau = cuoi
    ban_le = {}
    for c in doanh_thu_ban_le(tu, den):
        a = _rong()
        a["success"] = [c["don"], c.get("dt_ban", c["dt"])]
        a["returned"] = [c["tra"], c.get("dt_tra", 0.0)]
        a["don"], a["dt"] = c["don"] + c["tra"], a["success"][1] + a["returned"][1]
        ban_le[c["ten"]] = a
    return {"nv": nv, "san": san, "ban_le": ban_le}


def theo_trang_thai_cache(tu: str, den: str, gio: float = 6) -> dict:
    """Khoảng đã kết thúc (tháng trước) lưu `gio` giờ; khoảng có hôm nay luôn lấy mới."""
    if den >= date.today().isoformat():
        return theo_trang_thai(tu, den)
    f = Path(__file__).resolve().parent.parent / "data" / "nv_trang_thai_cache_v3.json"   # v3: thêm sàn + cửa hàng
    try:
        kho = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kho = {}
    khoa = f"{tu}_{den}"
    if khoa in kho and time.time() - kho[khoa]["luc"] < gio * 3600:
        return kho[khoa]["kq"]
    kq = theo_trang_thai(tu, den)
    kho[khoa] = {"luc": time.time(), "kq": kq}
    f.write_text(json.dumps(kho, ensure_ascii=False), encoding="utf-8")
    return kq


def _khoi(ten: str, a: dict, dong_nhom=NHOM) -> list[str]:
    dong = ["", f"• <b>{ten}</b>", f"  Tổng đơn: {a['don']} · Tổng doanh thu: <b>{vnd(a['dt'])}</b>"]
    for g, nh in dong_nhom:
        dong.append(f"  {nh}: {a[g][0]} đơn · {vnd(a[g][1])}")
    if a["khac"][0]:
        dong.append(f"  Trạng thái khác: {a['khac'][0]} đơn · {vnd(a['khac'][1])}")
    return dong


def _gop(ds) -> dict:
    t = _rong()
    for a in ds:
        t["don"] += a["don"]
        t["dt"] += a["dt"]
        for g in [g for g, _ in NHOM] + ["khac"]:
            t[g][0] += a[g][0]
            t[g][1] += a[g][1]
    return t


def soan_tin(kq: dict, nhan: str) -> str:
    """Tin Telegram (HTML)."""
    if "nv" not in kq:   # cache cũ (v2) chỉ có nhân viên
        kq = {"nv": kq, "san": {}, "ban_le": {}}
    dong = [f"<b>Doanh thu Nhanh.vn theo kênh — {nhan}</b>", "", "👩‍💼 <b>NHÂN VIÊN ONLINE</b>"]
    for ten, a in kq["nv"].items():
        dong += _khoi(ten, a)
    dong += _khoi("Tổng 3 nhân viên", _gop(kq["nv"].values()))
    san = {k: a for k, a in kq["san"].items() if a["don"]}
    if san:
        dong += ["", "🛍 <b>SÀN</b>"]
        for k, a in san.items():
            dong += _khoi(k, a)
        dong.append("  <i>Tiền hàng sau giảm giá; đơn khách trả sau khi giao thành công tính vào Hoàn.</i>")
    if kq["ban_le"]:
        dong += ["", "🏬 <b>BÁN LẺ TẠI CỬA HÀNG</b>"]
        for ten, a in kq["ban_le"].items():
            dong += ["", f"• <b>{ten}</b>",
                     f"  Bán: {a['success'][0]} phiếu · {vnd(a['success'][1])}",
                     f"  Khách trả: {a['returned'][0]} phiếu · {vnd(a['returned'][1])}",
                     f"  Doanh thu (đã trừ trả): <b>{vnd(a['success'][1] - a['returned'][1])}</b>"]
    tat = _gop([*kq["nv"].values(), *san.values(), *kq["ban_le"].values()])
    dong += ["", "💰 <b>TỔNG CÁC KÊNH</b>",
             f"  Tổng đơn: {tat['don']} · Tổng doanh thu: <b>{vnd(tat['dt'])}</b>"]
    for g, nh in NHOM:
        dong.append(f"  {nh}: {tat[g][0]} đơn · {vnd(tat[g][1])}")
    dong.append("  <i>Cửa hàng: phiếu bán tính vào Thành công, phiếu khách trả tính vào Hoàn.</i>")
    return "\n".join(dong)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    hom_nay = date.today()
    tu = sys.argv[1] if len(sys.argv) > 1 else hom_nay.replace(day=1).isoformat()
    den = sys.argv[2] if len(sys.argv) > 2 else hom_nay.isoformat()
    print(re.sub(r"</?[bi]>", "", soan_tin(theo_trang_thai(tu, den), f"{tu} → {den}")))


if __name__ == "__main__":
    main()
