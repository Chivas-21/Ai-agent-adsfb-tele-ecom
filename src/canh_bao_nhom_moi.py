"""Cảnh báo nhóm quảng cáo MỚI tiêu ≥ 40.000đ mà chưa ra tin nhắn — gửi Telegram nhóm "Ads L'amme", chờ /tat hoặc /giu.

Chủ trang (05/10/2026): "camp mới tạo tiêu đến 40k / ko ra mes => báo cáo / tắt / giữ, báo kèm chỉ số CPC + CPM của
nhóm qc đó".
- Nhóm mới = nhóm quảng cáo (adset) đang chạy (effective_status ACTIVE), tạo trong NGAY_MOI ngày gần nhất.
- Điều kiện: tổng chi từ lúc tạo (date_preset maximum) ≥ NGUONG_CHI và 0 cuộc trò chuyện
  (onsite_conversion.messaging_conversation_started_7d).
- Mỗi nhóm chỉ báo 1 lần (data/canh_bao_nhom_moi.json). Tin có số thứ tự; trả lời tin bằng /tat 1,2 (tắt nhóm —
  status PAUSED) hoặc /giu 1,2 (giữ chạy, không báo lại). Không trả lời tin thì lấy tin cảnh báo mới nhất.
- CPC = chi phí / lượt nhấp liên kết (cost_per_inline_link_click — với QC tin nhắn là nhấp "Gửi tin nhắn"), không có
  thì CPC (tất cả); CPM = chi phí / 1.000 lượt hiển thị.

Lịch Windows `\\LAMME\\CanhBaoNhomMoi` 3 tiếng/lần 8h–21h: 8h, 11h, 14h, 17h, 20h (chỉ gửi khi có nhóm mới chạm ngưỡng); bot có lệnh
/canhbao để xem ngay (liệt kê cả nhóm đã báo).

    python src/canh_bao_nhom_moi.py              # quét + gửi nhóm mới chạm ngưỡng
    python src/canh_bao_nhom_moi.py --dry-run    # in ra, không gửi, không đánh dấu đã báo
"""
import argparse
import html
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

import bao_cao_ads_telegram as bc
import fb_ads_create as fb
from nhanh_client import VN_TZ

NGUONG_CHI = 40_000
NGUONG_GIA_TIN = 60_000   # loại 2 (chủ trang thêm 06/10/2026): giá/tin nhắn > 60k mà 0 lượt mua
NGAY_MOI = 3
LY_DO = {"0tin": "đã chi ≥ 40.000đ mà 0 tin nhắn", "tin_dat": "giá tin nhắn > 60.000đ mà 0 lượt mua"}
FILE = Path(__file__).resolve().parent.parent / "data" / "canh_bao_nhom_moi.json"


def _doc() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"da_bao": {}, "ds": {}}


def _ghi(d: dict) -> None:
    FILE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _tat_ca(path: str, params: dict) -> list[dict]:
    kq = fb._goi("GET", path, params)
    rows = kq.get("data", [])
    while kq.get("paging", {}).get("next"):
        kq = requests.get(kq["paging"]["next"], timeout=60).json()
        rows += kq.get("data", [])
    return rows


def _so(r: dict, k: str) -> float:
    try:
        return float(r.get(k) or 0)
    except (TypeError, ValueError):
        return 0.0


def nhom_cham_nguong(nguong: float = NGUONG_CHI) -> list[dict]:
    """Nhóm mới đang chạy chạm 1 trong 2 điều kiện (trường "ly_do"):
    "0tin" — chi ≥ ngưỡng, 0 trò chuyện; "tin_dat" — có tin nhắn nhưng chi/tin > NGUONG_GIA_TIN và 0 lượt mua.
    Loại 0tin trước, trong mỗi loại chi nhiều nhất trước."""
    moc = datetime.now(VN_TZ) - timedelta(days=NGAY_MOI)
    ra = []
    for tk, acc in fb.TAI_KHOAN.items():
        try:
            nhom = [a for a in _tat_ca(f"act_{acc}/adsets", {
                        "fields": "id,name,created_time,campaign{name}",
                        "filtering": json.dumps([{"field": "effective_status", "operator": "IN", "value": ["ACTIVE"]}]),
                        "limit": 500})
                    if datetime.fromisoformat(a["created_time"]) >= moc]
            if not nhom:
                continue
            tao = {a["id"]: a for a in nhom}
            rows = []
            ids = list(tao)
            for i in range(0, len(ids), 50):
                rows += _tat_ca(f"act_{acc}/insights", {
                    "level": "adset", "date_preset": "maximum", "limit": 500,
                    "fields": "adset_id,adset_name,spend,actions,impressions,clicks,inline_link_clicks,cpc,cpm,"
                              "cost_per_inline_link_click",
                    "filtering": json.dumps([{"field": "adset.id", "operator": "IN", "value": ids[i:i + 50]}])})
        except RuntimeError as e:
            print(f"[{tk}] bỏ qua: {fb.an_bi_mat(e)}", file=sys.stderr)
            continue
        for r in rows:
            chi, tc, mua = _so(r, "spend"), bc._hanh_dong(r, bc.LOAI_TRO_CHUYEN), bc._hanh_dong(r, bc.LOAI_MUA)
            if chi >= nguong and tc == 0:
                ly_do = "0tin"
            elif tc > 0 and chi / tc > NGUONG_GIA_TIN and mua == 0:
                ly_do = "tin_dat"
            else:
                continue
            a = tao[r["adset_id"]]
            link_clicks = _so(r, "inline_link_clicks")
            ra.append({"id": r["adset_id"], "ly_do": ly_do, "tc": tc, "nhom": r.get("adset_name") or a["name"],
                       "camp": (a.get("campaign") or {}).get("name", ""), "tk": tk, "acc": acc,
                       "tao": datetime.fromisoformat(a["created_time"]).astimezone(VN_TZ).strftime("%H:%M %d/%m"),
                       "chi": chi, "hien_thi": _so(r, "impressions"), "nhap": link_clicks or _so(r, "clicks"),
                       "cpc": _so(r, "cost_per_inline_link_click") if link_clicks else _so(r, "cpc"),
                       "cpc_loai": "link" if link_clicks else "tất cả", "cpm": _so(r, "cpm")})
    return sorted(ra, key=lambda n: (n["ly_do"] != "0tin", -n["chi"]))


def soan(ds: list[dict], tieu_de: str, nguong: float = NGUONG_CHI) -> str:
    e = html.escape
    dong = [f"⚠️ <b>{e(tieu_de)}</b>",
            f"Nhóm tạo trong {NGAY_MOI} ngày, đang chạy (số liệu đến {datetime.now(VN_TZ):%H:%M %d/%m})"]
    if not ds:
        return "\n".join(dong + [f"Không có nhóm nào {LY_DO['0tin']} hoặc {LY_DO['tin_dat']}. 👍"])
    dong.append("Trả lời tin này: <code>/tat 1,2</code> tắt nhóm")   # chủ trang chỉ muốn 1 dòng này (05/10/2026)
    loai_truoc = None
    for i, n in enumerate(ds, 1):   # số thứ tự liền nhau qua 2 loại → /tat dùng chung
        ly_do = n.get("ly_do", "0tin")
        if ly_do != loai_truoc:
            dong += ([""] if dong[-1] else []) + [f"<b>{'🔴' if ly_do == '0tin' else '🟠'} {LY_DO[ly_do].capitalize()}</b>"]
            loai_truoc = ly_do
        link = f"https://adsmanager.facebook.com/adsmanager/manage/adsets?act={n['acc']}&selected_adset_ids={n['id']}"
        tin = ("0 tin nhắn" if ly_do == "0tin"
               else f"{n['tc']:.0f} tin · <b>{bc.vnd(n['chi'] / n['tc'])}/tin</b> · 0 mua")
        dong += [f"{i}. <a href=\"{link}\">{e(n['nhom'])}</a>",
                 f"    {n['tk']} · tạo {n['tao']} · chi <b>{bc.vnd(n['chi'])}</b> · {tin}",
                 f"    CPC ({n['cpc_loai']}): <b>{bc.vnd(n['cpc']) if n['cpc'] else '— (chưa có nhấp)'}</b>"
                 f" · CPM: <b>{bc.vnd(n['cpm'])}</b> · {n['hien_thi']:,.0f} hiển thị · {n['nhap']:,.0f} nhấp".replace(",", "."), ""]
    return "\n".join(dong)


def luu_ds(ds: list[dict], msg_id: int | None, danh_dau: bool = True) -> None:
    """Lưu danh sách theo message_id (cho /tat, /giu); danh_dau = ghi nhóm vào 'đã báo' để không báo lại."""
    d = _doc()
    khoa = str(msg_id or f"luc-{datetime.now():%Y%m%d%H%M%S}")
    d["ds"][khoa] = {"luc": f"{datetime.now():%H:%M %d/%m}",
                     "nhom": [{k: n[k] for k in ("id", "nhom", "tk", "acc", "chi")} for n in ds]}
    d["ds"] = dict(list(d["ds"].items())[-30:])
    d["cuoi"] = khoa
    if danh_dau:
        d["da_bao"].update({f"{n['id']}:{n.get('ly_do', '0tin')}": time.time() for n in ds})
        d["da_bao"] = {k: v for k, v in d["da_bao"].items() if time.time() - v < 30 * 86400}
    _ghi(d)


def doc_ds(msg_id: int | None = None) -> dict | None:
    d = _doc()
    return d["ds"].get(str(msg_id)) or d["ds"].get(d.get("cuoi", ""))


def ghi_giu(ids: list[str]) -> None:
    d = _doc()
    d.setdefault("giu", {}).update({i: time.time() for i in ids})
    _ghi(d)


def nhom_moi_can_bao() -> list[dict]:
    da = _doc()["da_bao"]   # khoá cũ (chỉ id) = đã báo loại 0 tin nhắn
    return [n for n in nhom_cham_nguong()
            if f"{n['id']}:{n['ly_do']}" not in da and not (n["ly_do"] == "0tin" and n["id"] in da)]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ds = nhom_moi_can_bao()
    if a.dry_run:
        print(soan(ds, "Cảnh báo nhóm quảng cáo mới"))
        return
    if not ds:
        print(f"[{datetime.now():%d/%m %H:%M}] không có nhóm mới chạm ngưỡng")
        return
    luu_ds(ds, bc.gui(soan(ds, "Cảnh báo nhóm quảng cáo mới")))
    print(f"[{datetime.now():%d/%m %H:%M}] đã báo {len(ds)} nhóm: " + ", ".join(n["id"] for n in ds))


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as e:  # traceback mặc định in URL kèm access_token vào log
        raise SystemExit(f"Lỗi mạng: {fb.an_bi_mat(e)}")
