"""Đối tượng đã lưu trên Meta (Ads Manager → Đối tượng → "Đối tượng đã lưu") → thêm vào danh sách đối tượng chọn được.

Chủ trang (10/10/2026): "update tệp đã lưu trên meta" — mục Đối tượng của trang "Yêu cầu lên camp FB" hiện thêm các
đối tượng team đã lưu trên các tài khoản QC Lamme. Meta không cho gắn thẳng saved audience vào nhóm QC qua API, nên
chép nguyên targeting của nó (tuổi, giới tính, vị trí, sở thích, tệp, loại trừ, Advantage+) sang khuôn DOI_TUONG.

Đối tượng có tệp / tệp loại trừ chỉ dùng được ở đúng tài khoản đã lưu (ID tệp khác nhau giữa các tài khoản); đối tượng
chỉ có sở thích dùng được ở mọi tài khoản. Mã: "luu_<tên không dấu>".

    python src/fb_tep_da_luu.py          # lấy lại từ Meta → data/fb_tep_da_luu.json, in danh sách
Trang dựng lại (html/fb-ads-yeu-cau/build.py) tự lấy lại; fb_doi_tuong đọc cache lúc import (không gọi mạng).
"""
import json
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "data" / "fb_tep_da_luu.json"
TRUONG = "id,name,targeting,time_updated"


def lay() -> dict:
    """Đọc saved_audiences của mọi tài khoản trong fb_ads_create.TAI_KHOAN, ghi cache."""
    import fb_ads_create as fb
    ds, loi = [], []
    for tk, acc in fb.TAI_KHOAN.items():
        try:
            r = fb._goi("GET", f"act_{acc}/saved_audiences", {"fields": TRUONG, "limit": 200})
        except Exception as e:  # noqa: BLE001
            loi.append(f"{tk}: {fb.an_bi_mat(str(e))[:120]}")
            continue
        ds += [{"tk": tk, "acc": acc, **a} for a in r.get("data", [])]
    kq = {"luc": time.time(), "ds": ds, "loi": loi}
    # Kiểm từng đối tượng với Meta (delivery_estimate, chỉ đọc): đối tượng lưu từ lâu có thể chứa loại trừ Meta đã bỏ
    # (vd "Uses a mobile device (less than 1 month)", lỗi 1870219) → thử bỏ phần loại trừ đó; vẫn lỗi thì ẩn đối tượng.
    for a, (ma, dt) in zip(ds, doi_tuong(kq).items()):
        for bo in (False, True):
            if bo and not dt.get("loai_tru_khac"):
                break
            d = {k: v for k, v in dt.items() if not (bo and k == "loai_tru_khac")}
            fb.DOI_TUONG[ma] = d
            try:
                fb._goi("GET", f"act_{a['acc']}/delivery_estimate", {
                    "optimization_goal": "CONVERSATIONS",
                    "targeting_spec": json.dumps(fb.dung_targeting(ma, a["acc"], False))})
                a.pop("hong", None)
                if bo:
                    a["bo_loai_tru_khac"] = True
                break
            except Exception as e:  # noqa: BLE001
                a["hong"] = fb.an_bi_mat(str(e))[:200]
            finally:
                fb.DOI_TUONG.pop(ma, None)
    FILE.write_text(json.dumps(kq, ensure_ascii=False, indent=1), encoding="utf-8")
    import fb_doi_tuong                      # nạp lại vào danh sách đang chạy (thay toàn bộ mã luu_ cũ)
    for ma in [m for m in fb_doi_tuong.DOI_TUONG if m.startswith("luu_")]:
        del fb_doi_tuong.DOI_TUONG[ma]
    for ma, dt in doi_tuong(kq).items():
        fb_doi_tuong.DOI_TUONG.setdefault(ma, dt)
    return kq


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    s = re.sub(r"[̀-ͯ]", "", s).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:32].rstrip("_") or "x"


def _gon(ds: list) -> list[dict]:
    return [{"id": str(x["id"]), "name": x.get("name", str(x["id"]))} for x in ds or []]


def doi_tuong(kq: dict | None = None) -> dict:
    """{mã: mục DOI_TUONG} từ cache (không gọi mạng). Cache chưa có → {}."""
    if kq is None:
        try:
            kq = json.loads(FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    ra: dict[str, dict] = {}
    for a in kq.get("ds", []):
        if a.get("hong"):                   # Meta không nhận targeting này nữa (xem lay())
            continue
        t = a.get("targeting") or {}
        acc = a["acc"]
        auto = (t.get("targeting_automation") or {}).get("advantage_audience")
        dt = {
            "ten_nhom": a["name"].strip(),
            "mo_ta": f"Đối tượng đã lưu trên Meta · {a['tk']} · sửa {a.get('time_updated', '')[:10]}",
            "tuoi": (t.get("age_min", 18), t.get("age_max", 65)), "adv": 1 if auto else 0,
            "gioi": t.get("genders"), "ngan_sach": 60_000, "nguon": "meta", "tk_luu": a["tk"],
        }
        if auto and t.get("age_range"):
            dt["goi_y"] = tuple(t["age_range"])
        if t.get("flexible_spec"):
            dt["so_thich"] = t["flexible_spec"]
        geo = {k: v for k, v in (t.get("geo_locations") or {}).items() if k != "location_types"}
        if geo != {"countries": ["VN"]}:
            dt["geo_goc"] = t["geo_locations"]
        if t.get("exclusions") and not a.get("bo_loai_tru_khac"):
            dt["loai_tru_khac"] = t["exclusions"]
        tep, ex = _gon(t.get("custom_audiences")), _gon(t.get("excluded_custom_audiences"))
        if tep or ex:                       # tệp gắn với tài khoản → chỉ dùng ở tài khoản đã lưu
            dt["tep"] = {acc: tep}
            if ex:
                dt["loai_tru_tep"] = {acc: ex}
        ma = "luu_" + _slug(a["name"])
        if ma in ra:
            ma += "_" + a["tk"]
        ra[ma] = dt
    return ra


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    kq = lay()
    for ma, dt in doi_tuong(kq).items():
        print(f"{ma:40} {dt['tk_luu']:8} {'chỉ ' + dt['tk_luu'] if 'tep' in dt else 'mọi TK':12} {dt['ten_nhom']}")
    for a in kq["ds"]:
        if a.get("hong") or a.get("bo_loai_tru_khac"):
            print(f"  ! {a['tk']} '{a['name']}': " + (f"ẩn — {a['hong']}" if a.get("hong") else "đã bỏ phần loại trừ Meta không còn nhận"))
    print(f"{len(kq['ds'])} đối tượng đã lưu, lúc {datetime.fromtimestamp(kq['luc']):%H:%M %d/%m}"
          + (" — lỗi: " + "; ".join(kq["loi"]) if kq["loi"] else ""))


if __name__ == "__main__":
    main()
