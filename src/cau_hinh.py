"""Hồ sơ doanh nghiệp cho AI AGENT — đọc config/doanh_nghiep.yaml (+ config/doi_tuong.yaml).

Mọi giá trị riêng của 1 doanh nghiệp (page, tài khoản QC, nhân viên, shop sàn, kênh Nhanh…) nằm trong 2 file YAML
này; code chỉ đọc qua đây để cùng 1 bộ code chạy cho nhiều doanh nghiệp (chủ trang yêu cầu đóng gói 19/10/2026).
Khoá / token vẫn ở config/.env. File khác: biến môi trường AGENT_CAU_HINH=<đường dẫn doanh_nghiep.yaml>
(doi_tuong.yaml đọc cùng thư mục).

    import cau_hinh
    cau_hinh.CH["meta"]["tai_khoan"]          # {"lamme1": "1189…", …}
    cau_hinh.lay("bao_cao.nhan_vien", [])      # đường dẫn chấm, có giá trị mặc định
"""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FILE = Path(os.getenv("AGENT_CAU_HINH") or ROOT / "config" / "doanh_nghiep.yaml")


def _doc(f: Path) -> dict:
    try:
        return yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raise SystemExit(f"Thiếu {f} — chép config/doanh_nghiep.mau.yaml thành file này rồi điền thông tin doanh nghiệp.")


CH: dict = _doc(FILE)
DOI_TUONG_FILE = FILE.with_name("doi_tuong.yaml")


def lay(duong: str, mac_dinh=None):
    """'meta.tai_khoan' → CH["meta"]["tai_khoan"]; thiếu khoá thì trả mac_dinh."""
    x = CH
    for k in duong.split("."):
        if not isinstance(x, dict) or k not in x:
            return mac_dinh
        x = x[k]
    return x


def doi_tuong() -> dict:
    """Nội dung config/doi_tuong.yaml ({} nếu chưa có)."""
    return _doc(DOI_TUONG_FILE) if DOI_TUONG_FILE.exists() else {}
