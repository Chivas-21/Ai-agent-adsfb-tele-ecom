"""Dựng trang "Yêu cầu lên camp FB" (artifact) từ template + dữ liệu hiện tại.

    python html/fb-ads-yeu-cau/build.py

Nhúng vào trang: danh mục, tài khoản QC, đối tượng (src/fb_doi_tuong.py) và danh sách sản phẩm
(data/commercial_engine.db). Chạy lại khi thêm đối tượng / sản phẩm mới, rồi nhờ Claude đăng lại
artifact (cùng link). Trang chỉ gửi yêu cầu về phiên Claude — không gọi Meta, không chứa token.
"""
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))

import fb_ads_create  # noqa: E402
import fb_bai_dang  # noqa: E402
from fb_ads_form import cau_hinh  # noqa: E402


def san_pham() -> list[list]:
    with sqlite3.connect(ROOT / "data" / "commercial_engine.db") as c:
        rows = c.execute("select sku, name from products where parent_id < 0 and status = 1 order by name").fetchall()
    return [[sku, ten] for sku, ten in rows]


def main() -> None:
    # Đối tượng đã lưu trên Meta (mã luu_…) — lấy lại mỗi lần dựng, kiểm với Meta, ẩn cái Meta không nhận
    import fb_tep_da_luu
    fb_tep_da_luu.lay()
    # Gợi ý nhắm mục tiêu cho "Target tự điền": cây Duyệt của Ads Manager + mục team hay dùng (gọi Meta lúc dựng)
    goi_y = fb_bai_dang.goi_y_cache()
    # Bài đăng từng chạy ads theo sản phẩm (mục 4) — cache 12 giờ, lấy lại mất ~6 phút; `--lam-moi-bai` để ép lấy lại
    bd = fb_bai_dang.bai_theo_san_pham_cache(lam_moi="--lam-moi-bai" in sys.argv)
    bai_gon = {ma: [{k: x[k] for k in ("post", "tin", "chi", "chi_moi_tin", "moi_nhat", "tai_khoan", "noi_dung")}
                    for x in ds] for ma, ds in bd["bai"].items()}
    # Bài viết trên page theo sản phẩm (mục 4, nút "Quét bài trên page") — cả bài chưa chạy ads; cache 12 giờ
    bp = fb_bai_dang.bai_page_cache(lam_moi="--lam-moi-page" in sys.argv)
    gon = lambda ds: [{k: x[k] for k in ("post", "ngay", "loai", "chia_se", "noi_dung")}  # noqa: E731
                      | {"cam_xuc": x.get("cam_xuc"), "binh_luan": x.get("binh_luan")} for x in ds]
    bai_page = {ma: gon(ds) for ma, ds in bp["bai"].items()}
    # Bài theo bộ sưu tập (ô tìm mục 2 gõ "BST …") — tên BST lấy từ chữ trong bài (fb_bai_dang.bai_theo_bst)
    bst = {ten: gon(ds) for ten, ds in bp.get("bst", {}).items()}

    # Mẫu cuộc trò chuyện (mục 7) — gom từ quảng cáo team đã chạy, cache 12 giờ
    import fb_mau_tro_chuyen
    mt = fb_mau_tro_chuyen.lay_mau_cache()
    tat = fb_mau_tro_chuyen.mau_all()  # "Mẫu tin nhắn all" — mặc định, đứng đầu danh sách
    mau = [{k: g.get(k) for k in ("id", "ten", "loi_chao", "cau_hoi", "so_qc", "gan_nhat", "vi_du")}
           for g in [tat] + [g for g in mt["mau"] if g["id"] != tat["id"]]]
    import cau_hinh as ch
    import mcp_lamme_fb
    du_lieu = {**cau_hinh(), "ten_dn": ch.lay("ten") or "", "mcp_host": mcp_lamme_fb.TEN, "tep_luu_luc": __import__("time").strftime("%H:%M %d/%m/%Y"), "san_pham": san_pham(), "goi_y": goi_y, "bai_dang": {"luc": bd["luc"], "bai": bai_gon},
               "mau_tro_chuyen": {"luc": mt["luc"], "mau": mau, "mac_dinh": tat["id"]}, "tinh": fb_ads_create.tinh_vn(),
               "pages": [{"id": pid, "ten": ten} for pid, ten in fb_ads_create.PAGES.values()],
               "bai_page": {"luc": bp["luc"], "so_bai": bp["so_bai"], "so_bai_page": bp.get("so_bai_page", {}),
                            "bai": bai_page, "bst": bst}}
    html = (HERE / "template.html").read_text(encoding="utf-8")
    js = json.dumps(du_lieu, ensure_ascii=False).replace("</", "<\\/")
    out = HERE / "fb-ads-yeu-cau.html"
    out.write_text(html.replace("/*__DU_LIEU__*/null", js), encoding="utf-8")
    print(f"{out} — {len(du_lieu['san_pham'])} sản phẩm, {len(du_lieu['doi_tuong'])} đối tượng, "
          f"{len(goi_y['cay'])} mục gợi ý, {len(goi_y['hay_dung'])} mục team hay dùng")


if __name__ == "__main__":
    main()
