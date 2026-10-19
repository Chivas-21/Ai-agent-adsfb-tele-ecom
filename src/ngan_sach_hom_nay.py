"""Ngân sách quảng cáo FB đã setup cho hôm nay — gửi Telegram nhóm "Ads L'amme" lúc 7h sáng.

Chủ trang (05/10/2026): "sáng 7h báo ngân sách ads đã setup cho hôm nay".
- Mọi tài khoản trong fb_ads_create.TAI_KHOAN; chỉ nhóm quảng cáo đang chạy (effective_status ACTIVE — chiến dịch,
  nhóm đều bật) và có lịch chạy trong hôm nay (start_time trước 24h hôm nay, end_time chưa qua).
- Chiến dịch dùng ngân sách chiến dịch (CBO) → tính ngân sách/ngày của chiến dịch 1 lần; không thì cộng ngân sách/ngày
  của từng nhóm đang chạy. Ngân sách trọn đời không cộng vào tổng/ngày — liệt kê riêng.
- Ngân sách là mức TỐI ĐA đã đặt; Facebook có thể chi lệch trong ngày (tới ~75% hơn mức ngày), tính trung bình theo tuần.

Lịch Windows `\\LAMME\\NganSach_07h` (7:00 hằng ngày); bot có lệnh /ngansachhomnay (thêm "chitiet" để xem đủ mọi chiến dịch).

    python src/ngan_sach_hom_nay.py              # gửi Telegram
    python src/ngan_sach_hom_nay.py --dry-run    # in ra, không gửi
"""
import argparse
import html
import json
import sys
from datetime import datetime, timedelta

import requests

import bao_cao_ads_telegram as bc
import fb_ads_create as fb
from nhanh_client import VN_TZ


def _tat_ca(path: str, params: dict) -> list[dict]:
    kq = fb._goi("GET", path, params)
    rows = kq.get("data", [])
    while kq.get("paging", {}).get("next"):
        kq = requests.get(kq["paging"]["next"], timeout=60).json()
        rows += kq.get("data", [])
    return rows


def _so(x) -> int:
    try:
        return int(x or 0)
    except (TypeError, ValueError):
        return 0


def ngan_sach() -> list[dict]:
    """[{tk, acc, ngay: tổng/ngày, camp: [{ten, ns, loai, so_nhom}], tron_doi: [...]}] theo tài khoản."""
    bay_gio = datetime.now(VN_TZ)
    het_ngay = bay_gio.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    dang = json.dumps([{"field": "effective_status", "operator": "IN", "value": ["ACTIVE"]}])
    ra = []
    for tk, acc in fb.TAI_KHOAN.items():
        try:
            nhom = _tat_ca(f"act_{acc}/adsets", {
                "fields": "id,campaign_id,campaign{name,daily_budget,lifetime_budget},daily_budget,lifetime_budget,"
                          "start_time,end_time", "filtering": dang, "limit": 500})
        except RuntimeError as e:
            print(f"[{tk}] bỏ qua: {fb.an_bi_mat(e)}", file=sys.stderr)
            continue
        camp: dict[str, dict] = {}
        for a in nhom:
            if a.get("start_time") and datetime.fromisoformat(a["start_time"]) >= het_ngay:
                continue   # hẹn chạy từ mai trở đi
            if a.get("end_time") and datetime.fromisoformat(a["end_time"]) <= bay_gio:
                continue   # đã hết lịch
            c = a.get("campaign") or {}
            x = camp.setdefault(a["campaign_id"], {"ten": c.get("name", "?"), "ns": 0, "tron_doi": 0, "so_nhom": 0,
                                                   "cbo": bool(_so(c.get("daily_budget")) or _so(c.get("lifetime_budget")))})
            x["so_nhom"] += 1
            if _so(c.get("daily_budget")):
                x["ns"] = _so(c["daily_budget"])
            elif _so(c.get("lifetime_budget")):
                x["tron_doi"] = _so(c["lifetime_budget"])
            else:
                x["ns"] += _so(a.get("daily_budget"))
                x["tron_doi"] += _so(a.get("lifetime_budget"))
        if camp:
            ds = sorted(camp.values(), key=lambda x: -x["ns"])
            ra.append({"tk": tk, "acc": acc, "ngay": sum(x["ns"] for x in ds), "camp": ds,
                       "tron_doi": sum(x["tron_doi"] for x in ds)})
    return sorted(ra, key=lambda t: -t["ngay"])


# Tin 7h / lệnh không tham số: chỉ tổng + từng tài khoản (chủ trang chốt 05/10/2026, bỏ cả top chiến dịch);
# "chitiet" mới liệt kê từng chiến dịch.
def soan(ds: list[dict], chi_tiet: bool = False) -> str:
    e = html.escape
    tong = sum(t["ngay"] for t in ds)
    so_camp = sum(len(t["camp"]) for t in ds)
    so_nhom = sum(x["so_nhom"] for t in ds for x in t["camp"])
    dong = [f"💸 <b>Ngân sách ads đã setup cho hôm nay {datetime.now(VN_TZ):%d/%m}</b> (lúc {datetime.now(VN_TZ):%H:%M})",
            f"Tổng ngân sách/ngày: <b>{bc.vnd(tong)}</b> · {so_camp} chiến dịch · {so_nhom} nhóm đang chạy"]
    tron_doi = sum(t["tron_doi"] for t in ds)
    if tron_doi:
        dong.append(f"+ ngân sách trọn đời (không tính vào/ngày): {bc.vnd(tron_doi)}")
    if not ds:
        return "\n".join(dong + ["Không có chiến dịch nào đang bật."])
    def _dong(x: dict, tk: str = "") -> str:
        ns = (bc.vnd(x["ns"]) if x["ns"] else "") + (f" trọn đời {bc.vnd(x['tron_doi'])}" if x["tron_doi"] else "")
        return (f"  • {e(x['ten'])}: <b>{ns.strip()}</b>" + (" (CBO)" if x["cbo"] else f" · {x['so_nhom']} nhóm")
                + (f" · {tk}" if tk else ""))
    dong.append("")
    for t in ds:
        dong.append(f"• <b>{t['tk']}</b>: <b>{bc.vnd(t['ngay'])}</b> · {len(t['camp'])} chiến dịch")
        if chi_tiet:
            dong += [_dong(x) for x in t["camp"]]
    if chi_tiet:
        dong += ["", "<i>Mức tối đa đã đặt — FB có thể chi lệch trong ngày. CBO = ngân sách chiến dịch.</i>"]
    return "\n".join(dong)


def bao_cao(chi_tiet: bool = False) -> str:
    return soan(ngan_sach(), chi_tiet)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    tin = bao_cao()
    if a.dry_run:
        print(tin)
    else:
        bc.gui(tin)
        print(f"[{datetime.now():%d/%m %H:%M}] đã gửi ngân sách hôm nay")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as e:  # traceback mặc định in URL kèm access_token vào log
        raise SystemExit(f"Lỗi mạng: {fb.an_bi_mat(e)}")
