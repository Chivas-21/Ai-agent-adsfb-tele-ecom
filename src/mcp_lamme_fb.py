"""MCP server "lamme-fb" (stdio) — cho trang artifact "Yêu cầu lên camp FB" tra dữ liệu Meta trên máy.

Trang gọi qua `host:lamme-fb` khi mở trong app Claude desktop. Chỉ có công cụ ĐỌC (tìm sản phẩm, bài đăng,
sở thích, tệp đối tượng); tạo chiến dịch vẫn do phiên Claude làm sau khi nhận yêu cầu. Token nằm ở config/.env,
không bao giờ trả ra ngoài.

Viết bằng thư viện chuẩn (không cần gói `mcp`): JSON-RPC 2.0, mỗi dòng một thông điệp trên stdin/stdout.
Thử tay:  echo {"jsonrpc":"2.0","id":1,"method":"tools/list"} | python src/mcp_lamme_fb.py
"""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fb_bai_dang  # noqa: E402

import cau_hinh  # noqa: E402

TEN = f"{cau_hinh.lay('ten_ngan') or 'agent'}-fb"
PHIEN_BAN = "1.0.0"


def _chuoi(mo_ta: str) -> dict:
    return {"type": "string", "description": mo_ta}


CONG_CU = {
    "tim_san_pham": {
        "description": "Tìm sản phẩm L'AMME (sản phẩm cha / lẻ) theo tên hoặc mã trong DB Nhanh.",
        "inputSchema": {"type": "object", "properties": {"q": _chuoi("Tên hoặc mã, ít nhất 2 ký tự")},
                        "required": ["q"]},
        "chay": lambda a: fb_bai_dang.tim_san_pham(a.get("q", "")),
    },
    "tim_bai_dang": {
        "description": "Các bài đăng từng chạy ads của 1 sản phẩm (khớp mã/tên trong tên chiến dịch hoặc quảng cáo, "
                       "2 tài khoản QC), kèm tin nhắn, chi phí/tin, đã chi — tốt nhất trước.",
        "inputSchema": {"type": "object", "properties": {"ma": _chuoi("Mã sản phẩm"), "ten": _chuoi("Tên sản phẩm")}},
        "chay": lambda a: fb_bai_dang.tim_bai_dang([a.get("ma", ""), a.get("ten", "")]),
    },
    "tim_so_thich": {
        "description": "Tra sở thích (interest) nhắm mục tiêu trên Meta theo tên, trả id + tên + nhóm.",
        "inputSchema": {"type": "object", "properties": {"q": _chuoi("Tên sở thích, VD: váy bầu")}, "required": ["q"]},
        "chay": lambda a: fb_bai_dang.tim_so_thich(a.get("q", "")),
    },
    "goi_y_lien_quan": {
        "description": "Meta gợi ý sở thích / hành vi / nhân khẩu học liên quan tới các mục đã chọn (truyền tên). "
                       "Mỗi mục có id, name, loai (khoá flexible_spec: interests, behaviors, family_statuses…).",
        "inputSchema": {"type": "object", "properties": {"ten": {"type": "array", "items": {"type": "string"},
                                                                 "description": "Tên các mục đã chọn"}},
                        "required": ["ten"]},
        "chay": lambda a: fb_bai_dang.goi_y_lien_quan(a.get("ten") or []),
    },
    "tim_tep": {
        "description": "Tìm tệp đối tượng tuỳ chỉnh / lookalike trong 1 tài khoản QC theo tên.",
        "inputSchema": {"type": "object", "properties": {"tai_khoan": _chuoi("Tên tài khoản QC (meta.tai_khoan trong config/doanh_nghiep.yaml)"),
                                                         "q": _chuoi("Một phần tên tệp, để trống = tất cả")},
                        "required": ["tai_khoan"]},
        "chay": lambda a: fb_bai_dang.tim_tep(a.get("tai_khoan", ""), a.get("q", "")),
    },
}


def _gui(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _xu_ly(msg: dict) -> dict | None:
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:  # notification (initialized, cancelled…) — không trả lời
        return None
    if method == "initialize":
        pv = (msg.get("params") or {}).get("protocolVersion") or "2024-11-05"
        return {"protocolVersion": pv, "capabilities": {"tools": {}},
                "serverInfo": {"name": TEN, "version": PHIEN_BAN}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{"name": k, "description": v["description"], "inputSchema": v["inputSchema"],
                           "annotations": {"readOnlyHint": True, "openWorldHint": True}}
                          for k, v in CONG_CU.items()]}
    if method == "tools/call":
        p = msg.get("params") or {}
        cc = CONG_CU.get(p.get("name"))
        if not cc:
            raise LookupError(f"Không có công cụ {p.get('name')}")
        try:
            kq = cc["chay"](p.get("arguments") or {})
        except Exception as e:  # noqa: BLE001 — lỗi Meta trả về trang dưới dạng tool error
            traceback.print_exc(file=sys.stderr)
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
        return {"content": [{"type": "text", "text": json.dumps(kq, ensure_ascii=False)}],
                "structuredContent": {"ket_qua": kq}}
    raise LookupError(f"Không hỗ trợ {method}")


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    for dong in sys.stdin:
        dong = dong.strip()
        if not dong:
            continue
        try:
            msg = json.loads(dong)
        except json.JSONDecodeError:
            _gui({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        try:
            kq = _xu_ly(msg)
            if kq is not None:
                _gui({"jsonrpc": "2.0", "id": msg["id"], "result": kq})
        except LookupError as e:
            _gui({"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32601, "message": str(e)}})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            _gui({"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": str(e)}})


if __name__ == "__main__":
    main()
