"""Mẫu "Cuộc trò chuyện" (lời chào + câu hỏi gợi ý) cho quảng cáo tin nhắn.

API "Mẫu đã lưu" của Ads Manager cần quyền pages_utility_messaging (token chưa có), nên danh sách mẫu được gom từ
chính các quảng cáo team đã chạy: trường creative.page_welcome_message, bỏ trùng theo lời chào + câu hỏi.
Gắn vào quảng cáo bằng creative {object_story_id, page_welcome_message} — Meta nhận (validate_only 30/09/2026).

    python src/fb_mau_tro_chuyen.py            # in danh sách mẫu (cache 12 giờ)
    python src/fb_mau_tro_chuyen.py --lam-moi  # lấy lại từ Meta
"""
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import fb_ads_create as fb

CACHE = Path(__file__).resolve().parent.parent / "data" / "mau_tro_chuyen_cache.json"
# "Mẫu tin nhắn all" (Mẫu đã lưu trên Ads Manager, không đọc được qua API) — mẫu MẶC ĐỊNH của trang yêu cầu.
# Dựng từ mẫu "quần Cici" team đã chạy 227 QC, đổi "mẫu quần Cici" → "mẫu sản phẩm" (02/10/2026).
# Mẫu tin nhắn chào mặc định của doanh nghiệp: config/mau_tin_nhan.json (mẫu: config/mau_tin_nhan.mau.json);
# chưa có thì dùng file cũ src/mau_tin_nhan_all.json
_CFG = Path(__file__).resolve().parent.parent / "config"
FILE_MAU_ALL = next((f for f in (_CFG / "mau_tin_nhan.json", Path(__file__).resolve().parent / "mau_tin_nhan_all.json",
                                 _CFG / "mau_tin_nhan.mau.json") if f.exists()), _CFG / "mau_tin_nhan.json")
SO_QC_MOI_TK = 1000  # quét ~1000 quảng cáo mới nhất mỗi tài khoản


def _doc(pwm: str) -> dict | None:
    try:
        j = json.loads(pwm)
    except (TypeError, ValueError):
        return None
    msg = ((j.get("text_format") or {}).get("message") or {})
    loi_chao = (msg.get("text") or "").strip()
    cau_hoi = [x.get("title", "") for x in msg.get("ice_breakers") or [] if x.get("title")]
    if not loi_chao and not cau_hoi:
        return None
    return {"loi_chao": loi_chao, "cau_hoi": cau_hoi}


def lay_mau(toi_da: int = 30) -> list[dict]:
    gom: dict[str, dict] = {}
    for tk, acc in fb.TAI_KHOAN.items():
        url = f"{fb.GRAPH}/act_{acc}/ads"
        p = {"fields": "created_time,name,creative{page_welcome_message}", "limit": 200, "access_token": fb._token()}
        da = 0
        import requests
        while url and da < SO_QC_MOI_TK:
            d = {}
            for lan in range(4):
                r = requests.get(url, params=p, timeout=120)
                d = r.json() if r.content else {}
                if r.status_code == 200 and "error" not in d:
                    break
                time.sleep(3 * (lan + 1))
            for a in d.get("data", []):
                pwm = (a.get("creative") or {}).get("page_welcome_message")
                m = _doc(pwm) if pwm else None
                if not m:
                    continue
                k = _khoa(m)
                g = gom.setdefault(k, {"id": k, **m, "so_qc": 0, "gan_nhat": "", "vi_du": a.get("name", ""),
                                       "tai_khoan": set(), "json": pwm})
                g["so_qc"] += 1
                g["tai_khoan"].add(tk)
                if a.get("created_time", "")[:10] > g["gan_nhat"]:
                    g["gan_nhat"], g["vi_du"], g["json"] = a["created_time"][:10], a.get("name", ""), pwm
            da += len(d.get("data", []))
            url, p = d.get("paging", {}).get("next"), None
    ds = sorted(gom.values(), key=lambda g: (g["gan_nhat"], g["so_qc"]), reverse=True)[:toi_da]
    for g in ds:
        g["tai_khoan"] = sorted(g["tai_khoan"])
    return ds


def _khoa(m: dict) -> str:
    return hashlib.sha1((m["loi_chao"] + "|" + "|".join(m["cau_hoi"])).encode("utf-8")).hexdigest()[:10]


def mau_all() -> dict:
    pwm = json.dumps(json.loads(FILE_MAU_ALL.read_text(encoding="utf-8")), ensure_ascii=False, separators=(",", ":"))
    m = _doc(pwm)
    return {"id": _khoa(m), "ten": "Mẫu tin nhắn all", **m, "so_qc": 0, "gan_nhat": "", "vi_du": "Mẫu đã lưu",
            "tai_khoan": [], "json": pwm}


def lay_mau_cache(toi_da_gio: float = 12, lam_moi: bool = False) -> dict:
    if not lam_moi and CACHE.exists() and time.time() - CACHE.stat().st_mtime < toi_da_gio * 3600:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    d = {"luc": datetime.now().strftime("%H:%M %d/%m/%Y"), "mau": lay_mau()}
    CACHE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def json_mau(ma: str) -> str:
    """Mã mẫu → chuỗi page_welcome_message để gắn vào creative. Không thấy → ValueError."""
    for g in [mau_all()] + lay_mau_cache(toi_da_gio=24 * 7)["mau"]:
        if g["id"] == ma:
            return g["json"]
    raise ValueError(f"không tìm thấy mẫu cuộc trò chuyện '{ma}' — dựng lại trang để cập nhật danh sách mẫu")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    d = lay_mau_cache(lam_moi="--lam-moi" in sys.argv)
    print(f"{len(d['mau'])} mẫu (lúc {d['luc']}):")
    for g in d["mau"]:
        print(f"  {g['id']}  {g['so_qc']:>3} QC, gần nhất {g['gan_nhat']}  {re.sub(chr(10), ' ', g['loi_chao'])[:70]}"
              + (f"  · hỏi: {' / '.join(g['cau_hoi'])}" if g["cau_hoi"] else ""))


if __name__ == "__main__":
    main()
