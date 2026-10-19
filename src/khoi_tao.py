"""Cài AI AGENT cho 1 doanh nghiệp mới — kiểm tra khoá và gợi ý cấu hình (chỉ ĐỌC, không tạo/sửa gì trên Meta/Nhanh).

    python src/khoi_tao.py --kiem-tra     # đủ file cấu hình chưa, token Meta / Nhanh / Telegram còn dùng được không
    python src/khoi_tao.py --meta         # in đoạn YAML pages + tai_khoan đọc từ token Meta để dán vào doanh_nghiep.yaml
    python src/khoi_tao.py --nhanh        # in kênh bán + kho trên Nhanh để điền nhanh.kenh_san / nhanh.kho

Chủ trang yêu cầu đóng gói "AI AGENT LAMME" cho các doanh nghiệp khác (19/10/2026). Hướng dẫn đầy đủ: docs/cai_dat.md.
"""
import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "config" / ".env")
GRAPH = "https://graph.facebook.com/v23.0"
QUYEN_CAN = {"ads_management", "ads_read", "pages_read_engagement", "pages_show_list", "business_management"}


def _an(s: str) -> str:
    import re
    return re.sub(r"(access_token=)[^&\s]+|EAA[A-Za-z0-9]{20,}", r"\1***", str(s))


def _meta(path: str, **p) -> dict:
    p["access_token"] = (os.getenv("META_ACCESS_TOKEN") or "").strip()
    return requests.get(f"{GRAPH}/{path}", params=p, timeout=60).json()


def kiem_tra() -> None:
    ok = True
    for f, mau in (("config/doanh_nghiep.yaml", "config/doanh_nghiep.mau.yaml"), ("config/doi_tuong.yaml", "config/doi_tuong.mau.yaml"),
                   ("config/.env", "config/.env.mau")):
        co = (ROOT / f).exists()
        ok &= co
        print(("  OK   " if co else "  THIẾU ") + f + ("" if co else f"  → chép từ {mau}"))
    if not os.getenv("META_ACCESS_TOKEN"):
        print("  THIẾU META_ACCESS_TOKEN trong config/.env")
    else:
        q = {x["permission"] for x in _meta("me/permissions").get("data", []) if x.get("status") == "granted"}
        thieu = QUYEN_CAN - q
        print("  Meta: " + ("đủ quyền" if not thieu else "thiếu quyền " + ", ".join(sorted(thieu))))
        app = _meta("debug_token", input_token=os.getenv("META_ACCESS_TOKEN")).get("data", {})
        print(f"  Meta app: {app.get('application')} ({app.get('app_id')}) · hết hạn: {app.get('expires_at') or 'không'}")
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        r = requests.get(f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/getMe", timeout=30).json()
        print("  Telegram: " + (("@" + r["result"]["username"]) if r.get("ok") else "token sai"))
    else:
        print("  THIẾU TELEGRAM_BOT_TOKEN (báo cáo Telegram sẽ không chạy)")
    if os.getenv("NHANH_ACCESS_TOKEN"):
        try:
            sys.path.insert(0, str(ROOT / "src"))
            from nhanh_client import NhanhClient
            NhanhClient().check_token()
            print("  Nhanh: token dùng được")
        except Exception as e:  # noqa: BLE001
            print("  Nhanh: lỗi " + _an(e)[:200])
    else:
        print("  THIẾU NHANH_ACCESS_TOKEN")
    if ok:
        sys.path.insert(0, str(ROOT / "src"))
        import cau_hinh
        print(f"  Doanh nghiệp: {cau_hinh.lay('ten')} · {len(cau_hinh.lay('meta.pages') or {})} page · "
              f"{len(cau_hinh.lay('meta.tai_khoan') or {})} tài khoản QC · "
              f"{len((cau_hinh.doi_tuong().get('doi_tuong') or {}))} đối tượng")


def goi_y_meta() -> None:
    pages = _meta("me/accounts", fields="id,name", limit=100).get("data", [])
    tk = _meta("me/adaccounts", fields="account_id,name,account_status", limit=200).get("data", [])
    print("  pages:")
    for i, p in enumerate(pages, 1):
        print(f'    page{i}: {{id: "{p["id"]}", ten: "{p["name"]}"}}')
    print("  tai_khoan:")
    for i, a in enumerate(tk, 1):
        trang_thai = "" if a.get("account_status") == 1 else "   # không hoạt động"
        print(f'    tk{i}: "{a["account_id"]}"   # {a.get("name", "")}{trang_thai}')


def goi_y_nhanh() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from nhanh_client import NhanhClient
    c = NhanhClient()
    for path, nhan in (("product/depot", "kho"), ("order/salechannel", "kenh_ban")):
        try:
            print(nhan, c.call(path, {}).get("data"))
        except Exception as e:  # noqa: BLE001
            print(nhan, "không đọc được:", _an(e)[:150])


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--kiem-tra", action="store_true")
    ap.add_argument("--meta", action="store_true")
    ap.add_argument("--nhanh", action="store_true")
    a = ap.parse_args()
    if a.meta:
        goi_y_meta()
    elif a.nhanh:
        goi_y_nhanh()
    else:
        kiem_tra()


if __name__ == "__main__":
    main()
