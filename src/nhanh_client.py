"""
Client Nhanh.vn Open API v3.0 (https://apidocs.nhanh.vn/v3/readme.md).

- Base URL: https://pos.open.nhanh.vn/v3.0/{path}?appId=..&businessId=..
- Header Authorization: accessToken; body JSON {filters, paginator, dataOptions}
- Phân trang kiểu cursor: truyền lại nguyên object paginator.next của response trước
- Rate limit 150 request / 30 giây / (appId + businessId + URL); ERR_429 trả về unlockedAt
- order/list chỉ cho lọc tối đa 31 ngày mỗi lần -> list_orders tự chia cửa sổ 30 ngày
- accessToken hạn 1 năm, không có refresh token -> check_token() để cảnh báo sớm
"""
import datetime as dt
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_URL = "https://pos.open.nhanh.vn/v3.0"
ENV_PATH = Path(__file__).resolve().parent.parent / "config" / ".env"
VN_TZ = dt.timezone(dt.timedelta(hours=7))

load_dotenv(ENV_PATH)


class NhanhAPIError(RuntimeError):
    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code


class NhanhClient:
    def __init__(self):
        self.app_id = os.getenv("NHANH_APP_ID")
        self.business_id = os.getenv("NHANH_BUSINESS_ID")
        self.access_token = os.getenv("NHANH_ACCESS_TOKEN")
        self.secret_key = os.getenv("NHANH_SECRET_KEY")
        missing = [k for k, v in {
            "NHANH_APP_ID": self.app_id,
            "NHANH_BUSINESS_ID": self.business_id,
            "NHANH_ACCESS_TOKEN": self.access_token,
        }.items() if not v]
        if missing:
            raise NhanhAPIError(f"Thiếu trong config/.env: {', '.join(missing)} — chạy src/get_access_token.py")
        self.session = requests.Session()

    def call(self, path: str, body: dict | None = None, max_retries: int = 5) -> dict:
        url = f"{BASE_URL}/{path}"
        params = {"appId": self.app_id, "businessId": self.business_id}
        headers = {"Authorization": self.access_token, "Content-Type": "application/json"}
        for _ in range(max_retries):
            resp = self.session.post(url, params=params, headers=headers, json=body or {}, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 1:
                return data
            error_code = data.get("errorCode")
            if error_code in ("ERR_429", "ERR_EXCEEDED_RATE_LIMIT"):
                unlocked_at = (data.get("data") or {}).get("unlockedAt") or (time.time() + 30)
                time.sleep(max(1, unlocked_at - time.time() + 1))
                continue
            raise NhanhAPIError(f"{path}: {error_code} {data.get('messages') or data.get('message')}", error_code)
        raise NhanhAPIError(f"{path}: vẫn bị rate limit sau {max_retries} lần thử", "ERR_429")

    def paginate(self, path: str, filters: dict | None = None, size: int = 100,
                 data_options: dict | None = None, pause: float = 0.25):
        """Yield từng bản ghi qua mọi trang (cursor paginator.next)."""
        next_cursor = None
        while True:
            paginator = {"size": size}
            if next_cursor:
                paginator["next"] = next_cursor
            body = {"filters": filters or {}, "paginator": paginator}
            if data_options:
                body["dataOptions"] = data_options
            resp = self.call(path, body)
            yield from resp.get("data") or []
            next_cursor = (resp.get("paginator") or {}).get("next")
            if not next_cursor:
                return
            time.sleep(pause)  # giữ dưới 150 request / 30 giây

    # --- Endpoint dùng trong Commercial Engine ---

    def list_orders(self, start: dt.datetime, end: dt.datetime, by: str = "createdAt"):
        """by = createdAt (đơn mới) hoặc updatedAt (đơn đổi trạng thái: giao, hoàn, hủy)."""
        window = dt.timedelta(days=30)
        cursor = start
        while cursor < end:
            window_end = min(cursor + window, end)
            filters = {f"{by}From": int(cursor.timestamp()), f"{by}To": int(window_end.timestamp())}
            yield from self.paginate("order/list", filters, size=100)
            cursor = window_end

    def list_products(self, **filters):
        yield from self.paginate("product/list", filters, size=100)

    def list_inventory(self, **filters):
        yield from self.paginate("product/inventory", filters, size=100)

    def check_token(self) -> dict:
        return self.call("app/checkaccesstoken", {"secretKey": self.secret_key}).get("data", {})
