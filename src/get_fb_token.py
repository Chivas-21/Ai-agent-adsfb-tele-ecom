"""Đổi token Facebook ngắn hạn (1-2 tiếng) thành token dài hạn (~60 ngày), và kiểm tra token.

Token dài hạn dùng cho apps_script/CpAdsFB.gs — dán vào Apps Script >
Cài đặt dự án > Thuộc tính tập lệnh, khoá META_ACCESS_TOKEN.

Chạy:
    python src/get_fb_token.py              # đổi token ngắn -> dài (hỏi token, không hiện lên màn hình)
    python src/get_fb_token.py --check      # xem token hiện tại còn bao nhiêu ngày
    python src/get_fb_token.py --check --token <token>

Cần trong config/.env (lấy ở developers.facebook.com > App > Cài đặt > Cơ bản):
    FB_APP_ID=...
    FB_APP_SECRET=...

Script KHÔNG ghi token ra file và KHÔNG gửi đi đâu ngoài graph.facebook.com.
"""
import argparse
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "config" / ".env")

GRAPH = "https://graph.facebook.com/v23.0"
sys.path.insert(0, str(ROOT / "src"))
import cau_hinh  # noqa: E402

# Tài khoản QC kiểm quyền sau khi lấy token (config/doanh_nghiep.yaml → meta.tai_khoan_quet_bai)
AD_ACCOUNTS = [str(cau_hinh.lay("meta.tai_khoan", {})[t]) for t in (cau_hinh.lay("meta.tai_khoan_quet_bai") or [])]


def _need(key: str) -> str:
    v = os.getenv(key)
    if not v:
        raise SystemExit(
            f"Thiếu {key} trong config/.env.\n"
            "Lấy ở developers.facebook.com > App của bạn > Cài đặt > Cơ bản."
        )
    return v.strip()


def _get(path: str, params: dict) -> dict:
    r = requests.get(f"{GRAPH}/{path}", params=params, timeout=30)
    data = r.json() if r.content else {}
    if r.status_code != 200 or "error" in data:
        err = data.get("error", {})
        raise SystemExit(
            f"Meta trả lỗi {r.status_code} (code {err.get('code')}): {err.get('message', r.text[:300])}"
        )
    return data


def doi_token_dai_han(short_token: str) -> dict:
    """Trả về {access_token, expires_in} — token dài hạn ~60 ngày."""
    return _get(
        "oauth/access_token",
        {
            "grant_type": "fb_exchange_token",
            "client_id": _need("FB_APP_ID"),
            "client_secret": _need("FB_APP_SECRET"),
            "fb_exchange_token": short_token,
        },
    )


def soi_token(token: str) -> dict:
    """debug_token: xem hạn dùng + quyền của token."""
    app_token = f"{_need('FB_APP_ID')}|{_need('FB_APP_SECRET')}"
    res = _get("debug_token", {"input_token": token, "access_token": app_token})
    return res.get("data", {})


def kiem_tra_tai_khoan(token: str) -> list[str]:
    """Thử đọc từng tài khoản quảng cáo để chắc token dùng được thật."""
    ket_qua = []
    for acc in AD_ACCOUNTS:
        try:
            tt = _get(f"act_{acc}", {"fields": "name,currency", "access_token": token})
            ket_qua.append(f"  OK  {acc} — {tt.get('name')} ({tt.get('currency')})")
        except SystemExit as e:
            ket_qua.append(f"  LỖI {acc} — {e}")
    return ket_qua


def _in_han(data: dict) -> None:
    het = data.get("expires_at")
    if not het:
        print("Hạn dùng: không hết hạn")
        return
    khi = datetime.fromtimestamp(het, tz=timezone.utc).astimezone()
    con = (khi - datetime.now(timezone.utc).astimezone()).days
    print(f"Hạn dùng: {khi:%d/%m/%Y %H:%M} (còn {con} ngày)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="Chỉ kiểm tra token, không đổi")
    ap.add_argument("--token", help="Token cần kiểm tra (mặc định lấy META_ACCESS_TOKEN trong .env)")
    args = ap.parse_args()

    if args.check:
        token = args.token or os.getenv("META_ACCESS_TOKEN")
        if not token:
            token = getpass.getpass("Dán token cần kiểm tra (không hiện lên màn hình): ").strip()
        if not token:
            raise SystemExit("Chưa nhập token.")

        data = soi_token(token)
        print(f"App ID: {data.get('app_id')}  |  loại: {data.get('type')}")
        print(f"Còn hiệu lực: {'có' if data.get('is_valid') else 'KHÔNG'}")
        _in_han(data)
        quyen = data.get("scopes", [])
        print(f"Quyền: {', '.join(quyen) if quyen else '(trống)'}")
        if "ads_read" not in quyen:
            print("CẢNH BÁO: thiếu quyền ads_read — script trên Apps Script sẽ không đọc được insights.")
        print("Tài khoản quảng cáo:")
        for d in kiem_tra_tai_khoan(token):
            print(d)
        return

    print("Lấy token ngắn hạn ở Graph API Explorer (nhớ tích quyền ads_read),")
    print("rồi dán vào đây. Ký tự sẽ không hiện lên màn hình.\n")
    short = getpass.getpass("Token ngắn hạn: ").strip()
    if not short:
        raise SystemExit("Chưa nhập token.")

    kq = doi_token_dai_han(short)
    dai = kq["access_token"]

    print("\n=== TOKEN DÀI HẠN (copy nguyên dòng dưới) ===")
    print(dai)
    print("=== hết ===\n")

    data = soi_token(dai)
    _in_han(data)
    print(f"Quyền: {', '.join(data.get('scopes', [])) or '(trống)'}")
    print("Tài khoản quảng cáo:")
    for d in kiem_tra_tai_khoan(dai):
        print(d)

    print(
        "\nDán token trên vào: Apps Script > Cài đặt dự án > Thuộc tính tập lệnh"
        "\n  Khoá:      META_ACCESS_TOKEN"
        "\n  Giá trị:   <token vừa in>"
        "\nRồi chạy kiemTraKetNoiAds() trên Apps Script để xác nhận."
        "\nĐừng lưu token vào config/.env hay commit vào git."
    )


if __name__ == "__main__":
    main()
