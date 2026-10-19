"""
Lấy (hoặc gia hạn) accessToken Nhanh v3 và ghi vào config/.env. Token hạn 1 năm, không có refresh.

1. Mở: https://nhanh.vn/oauth?appId=<NHANH_APP_ID>&returnLink=<NHANH_RETURN_LINK>
2. Chọn quyền (chỉ quyền đọc) + chọn đủ các kho -> Đồng ý
3. Copy giá trị accessCode trên thanh địa chỉ (hạn 10 phút), chạy:
       python src/get_access_token.py <accessCode>

Lưu ý: v3 chỉ giữ 1 token cho mỗi appId + businessId; token cũ hết hiệu lực sau 15 phút.
"""
import datetime as dt
import os
import re
import sys
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from nhanh_client import ENV_PATH, VN_TZ

load_dotenv(ENV_PATH)


def update_env(values: dict):
    text = ENV_PATH.read_text(encoding="utf-8-sig") if ENV_PATH.exists() else ""
    for key, val in values.items():
        line = f"{key}={val}"
        pattern = re.compile(rf"^{key}=.*$", re.MULTILINE)
        text = pattern.sub(line, text) if pattern.search(text) else text.rstrip("\n") + f"\n{line}\n"
    ENV_PATH.write_text(text, encoding="utf-8")


def main():
    app_id = os.getenv("NHANH_APP_ID")
    secret_key = os.getenv("NHANH_SECRET_KEY")
    return_link = os.getenv("NHANH_RETURN_LINK")
    if len(sys.argv) < 2:
        print(__doc__)
        print(f"Link cấp quyền: https://nhanh.vn/oauth?appId={app_id}&returnLink={quote(return_link or '', safe='')}")
        return

    resp = requests.post(
        f"https://pos.open.nhanh.vn/v3.0/app/getaccesstoken?appId={app_id}",
        json={"accessCode": sys.argv[1].strip(), "secretKey": secret_key},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 1:
        raise SystemExit(f"Đổi accessCode thất bại: {body.get('errorCode')} {body.get('messages')}")

    data = body["data"]
    update_env({
        "NHANH_ACCESS_TOKEN": data["accessToken"],
        "NHANH_BUSINESS_ID": data["businessId"],
        "NHANH_TOKEN_EXPIRES_AT": data["expiredAt"],
    })
    expires = dt.datetime.fromtimestamp(int(data["expiredAt"]), tz=VN_TZ)
    print(f"Đã lưu token mới. businessId={data['businessId']} | hết hạn {expires:%d/%m/%Y} | kho: {data.get('depotIds')}")


if __name__ == "__main__":
    main()
