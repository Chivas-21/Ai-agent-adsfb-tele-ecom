"""Đề xuất nhân nhóm quảng cáo — gửi Telegram nhóm "Ads L'amme" (cùng bot với báo cáo ads).

Nhóm quảng cáo (adset) trong ngày hôm nay, ở mọi tài khoản trong fb_ads_create.TAI_KHOAN, thoả CẢ HAI:
    chi phí / lượt mua  < 100.000đ   (có ít nhất 1 lượt mua)
    chi phí / tin nhắn  <  30.000đ   (có ít nhất 1 cuộc trò chuyện)
→ liệt kê, rẻ nhất / lượt mua trước, kèm link mở nhóm trên Ads Manager. Ngưỡng chốt với chủ trang 03/10/2026
(Facebook không ghi giá trị đơn nên dùng chi phí / lượt mua).

Lịch Windows `\\LAMME\\DeXuatNhan_<giờ>h` lúc 10h, 12h, 14h, 16h, 17h; bot Telegram có lệnh /nhan để xem bất kỳ lúc nào.

    python src/de_xuat_nhan_nhom.py                 # gửi Telegram
    python src/de_xuat_nhan_nhom.py --dry-run       # in ra màn hình, không gửi
    python src/de_xuat_nhan_nhom.py --mua 80000 --tin 25000
"""
import argparse
import html
import json
import sys
from pathlib import Path
from datetime import date, datetime

import requests

import bao_cao_ads_telegram as bc
import fb_ads_create as fb
import nhan_nhom
from nhanh_client import VN_TZ

NGUONG_MUA = 100_000
NGUONG_TIN = 30_000
# Danh sách đã gửi lên nhóm: số thứ tự trong tin → nhóm quảng cáo; lệnh /nhanban đọc lại (trả lời đúng tin, hoặc tin mới nhất)
FILE_DS = Path(__file__).resolve().parent.parent / "data" / "de_xuat_nhan_ds.json"


def luu_ds(dat: list[dict], msg_id: int | None) -> None:
    try:
        d = json.loads(FILE_DS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {"ds": {}}
    khoa = str(msg_id or f"luc-{datetime.now():%Y%m%d%H%M%S}")
    d["ds"][khoa] = {"luc": f"{datetime.now():%H:%M %d/%m}",
                     "nhom": [{k: n[k] for k in ("id", "nhom", "camp", "acc", "tk", "chi", "mua", "tc")} for n in dat]}
    d["ds"] = dict(list(d["ds"].items())[-30:])
    d["cuoi"] = khoa
    FILE_DS.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def doc_ds(msg_id: int | None = None) -> dict | None:
    """Danh sách của tin msg_id (người dùng trả lời đúng tin đề xuất); không có thì lấy tin mới nhất."""
    try:
        d = json.loads(FILE_DS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d["ds"].get(str(msg_id)) or d["ds"].get(d.get("cuoi", ""))


def lay_nhom_hom_nay() -> list[dict]:
    h = date.today().isoformat()
    ra = []
    for ten, acc in fb.TAI_KHOAN.items():
        try:
            kq = fb._goi("GET", f"act_{acc}/insights", {
                "level": "adset", "fields": "adset_id,adset_name,campaign_name,spend,actions",
                "time_range": {"since": h, "until": h}, "limit": 500})
        except RuntimeError as e:
            print(f"[{ten}] bỏ qua: {e}", file=sys.stderr)
            continue
        rows = kq.get("data", [])
        while kq.get("paging", {}).get("next"):
            kq = requests.get(kq["paging"]["next"], timeout=60).json()
            rows += kq.get("data", [])
        for r in rows:
            ra.append({"tk": ten, "acc": acc, "id": r["adset_id"], "nhom": r["adset_name"], "camp": r["campaign_name"],
                       "chi": float(r.get("spend", 0)), "tc": bc._hanh_dong(r, bc.LOAI_TRO_CHUYEN),
                       "mua": bc._hanh_dong(r, bc.LOAI_MUA)})
    return ra


def loc(nhom: list[dict], nguong_mua: float, nguong_tin: float) -> list[dict]:
    dat = [n for n in nhom if n["mua"] >= 1 and n["tc"] >= 1
           and n["chi"] / n["mua"] < nguong_mua and n["chi"] / n["tc"] < nguong_tin]
    return sorted(dat, key=lambda n: n["chi"] / n["mua"])


def soan(dat: list[dict], so_nhom: int, nguong_mua: float, nguong_tin: float) -> str:
    e = html.escape
    dau = [f"🚀 <b>Đề xuất nhân nhóm — hôm nay {date.today():%d/%m} (số liệu đến {datetime.now(VN_TZ):%H:%M})</b>",
           f"Điều kiện: chi phí/lượt mua &lt; {bc.vnd(nguong_mua)} và chi phí/tin nhắn &lt; {bc.vnd(nguong_tin)}"]
    if not dat:
        return "\n".join(dau + [f"Chưa có nhóm nào đạt (đã xét {so_nhom} nhóm có chi tiêu hôm nay)."])
    dong = dau + [f"<b>{len(dat)}</b>/{so_nhom} nhóm đạt — muốn nhân thì trả lời tin này: <code>/nhanban 1,2,3</code>", ""]
    da_nhan = nhan_nhom.da_nhan_hom_nay()   # nhóm đã có lệnh nhân trong ngày (qua bot)
    for i, n in enumerate(dat, 1):
        link = (f"https://adsmanager.facebook.com/adsmanager/manage/adsets?act={n['acc']}"
                f"&selected_adset_ids={n['id']}")
        dong.append(f"{i}. <a href=\"{link}\">{e(n['nhom'])}</a>\n"
                    f"    {n['tk']} · chi {bc.vnd(n['chi'])} · <b>{n['mua']:.0f} mua ({bc.gia(n['chi'], n['mua'])}/mua)</b>"
                    f" · {n['tc']:.0f} TC ({bc.gia(n['chi'], n['tc'])}/TC)"
                    + (f"\n    💰 {n['ns']}" if n.get("ns") else "")
                    + (" · ✅ <b>đã nhân camp</b>" if n["id"] in da_nhan else ""))
    return "\n".join(dong)


def _ngan_sach(adset_id: str) -> str:
    """'NS nhóm 130.000đ/ngày' | 'NS chiến dịch 500.000đ/ngày (CBO)' | tổng trọn đời; lỗi thì để trống."""
    try:
        a = fb._goi("GET", adset_id, {"fields": "daily_budget,lifetime_budget,campaign{daily_budget,lifetime_budget}"})
    except RuntimeError:
        return ""
    c = a.get("campaign") or {}
    so = lambda x: int(x) if x not in (None, "", "0") else 0  # noqa: E731
    if so(a.get("daily_budget")):
        return f"NS nhóm {bc.vnd(so(a['daily_budget']))}/ngày"
    if so(a.get("lifetime_budget")):
        return f"NS nhóm {bc.vnd(so(a['lifetime_budget']))} trọn đời"
    if so(c.get("daily_budget")):
        return f"NS chiến dịch {bc.vnd(so(c['daily_budget']))}/ngày (CBO)"
    if so(c.get("lifetime_budget")):
        return f"NS chiến dịch {bc.vnd(so(c['lifetime_budget']))} trọn đời (CBO)"
    return ""


def bao_cao(nguong_mua: float = NGUONG_MUA, nguong_tin: float = NGUONG_TIN) -> tuple[str, list[dict]]:
    """(nội dung tin, danh sách nhóm đạt theo đúng số thứ tự trong tin)."""
    nhom = lay_nhom_hom_nay()
    dat = loc(nhom, nguong_mua, nguong_tin)
    for n in dat:  # chỉ tra ngân sách cho các nhóm đạt (vài chục lệnh gọi, không phải cả trăm nhóm)
        n["ns"] = _ngan_sach(n["id"])
    return soan(dat, sum(1 for n in nhom if n["chi"] > 0), nguong_mua, nguong_tin), dat


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--mua", type=float, default=NGUONG_MUA, help="ngưỡng chi phí/lượt mua (đ)")
    ap.add_argument("--tin", type=float, default=NGUONG_TIN, help="ngưỡng chi phí/tin nhắn (đ)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    tin, dat = bao_cao(a.mua, a.tin)
    if a.dry_run:
        print(tin)
    else:
        luu_ds(dat, bc.gui(tin))
        print("Đã gửi Telegram.")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as e:  # traceback mặc định in URL kèm access_token vào log
        raise SystemExit(f"Lỗi mạng: {fb.an_bi_mat(e)}")
