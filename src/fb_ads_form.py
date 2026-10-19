"""Form lên chiến dịch Facebook Ads — chạy trên máy, mở http://localhost:8766

    python src/fb_ads_form.py              # mở form trong trình duyệt
    python src/fb_ads_form.py --khong-mo   # chỉ chạy server

Form gọi lại đúng logic của fb_ads_create.py (khuôn tên, đối tượng, chiến dịch TẮT / nhóm + QC BẬT).
Token nằm trong config/.env, không bao giờ gửi ra trình duyệt. Server chỉ nghe 127.0.0.1.
Mỗi lần tạo được ghi thêm vào reports/fb_ads_da_tao.csv.
"""
import argparse
import csv
import json
import sys
import traceback
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import fb_ads_create as fb
import fb_bai_dang
from fb_doi_tuong import DOI_TUONG, MAC_DINH

ROOT = Path(__file__).resolve().parent.parent
TRANG = ROOT / "html" / "fb-ads-form" / "index.html"
NHAT_KY = ROOT / "reports" / "fb_ads_da_tao.csv"
CONG = 8766
# Trình duyệt không tự gửi header lạ sang localhost từ trang web khác (bị CORS chặn),
# nên đòi header này là đủ chặn trang lạ bấm hộ nút Tạo.
HEADER_BAT_BUOC = "X-Lamme"


def cau_hinh() -> dict:
    ds = []
    for ma, dt in DOI_TUONG.items():
        ban = {tk: fb.dung_targeting(ma, acc, False) for tk, acc in fb.TAI_KHOAN.items()
               if "tep" not in dt or acc in dt["tep"]}
        dau = next(iter(ban.values()))
        ds.append({
            "ma": ma, "ten_nhom": dt["ten_nhom"], "mo_ta": dt["mo_ta"], "ngan_sach": dt["ngan_sach"],
            "ten_target": fb.ten_target(dau, dt),
            "chi_tiet": {tk: fb.chi_tiet_nham_vao(t) for tk, t in ban.items()},
            "tai_khoan": list(ban), "nguon": dt.get("nguon", ""),
        })
    return {"danh_muc": fb.DANH_MUC, "tai_khoan": list(fb.TAI_KHOAN), "tai_khoan_mac_dinh": fb.TAI_KHOAN_MAC_DINH,
            "doi_tuong": ds, "mac_dinh": MAC_DINH, "hau_to": fb.HAU_TO_MAC_DINH}


def form_sang_dong(d: dict) -> list[dict]:
    """Dữ liệu form → các dòng giống CSV của fb_ads_create."""
    dt = [x for x in d.get("doi_tuong", []) if x.get("ma")]
    if not dt:
        raise ValueError("Chưa chọn đối tượng nào.")
    phan = [f"{x['ma']}:{int(x['ngan_sach'])}" if x.get("ngan_sach") else x["ma"] for x in dt]
    bat_dau = (d.get("bat_dau") or "").replace("T", " ")
    chung = {"ma": d.get("ma", ""), "danh_muc": d.get("danh_muc", ""), "ten": d.get("ten", ""),
             "post": d.get("post", ""), "tai_khoan": d.get("tai_khoan", ""),
             "loai_tru": "1" if d.get("loai_tru") else "", "bat_dau": bat_dau}
    for k in ("ma", "ten", "post"):
        if not str(chung[k]).strip():
            raise ValueError({"ma": "Thiếu mã sản phẩm.", "ten": "Thiếu tên sản phẩm.",
                              "post": "Chưa chọn bài đăng."}[k])
    if d.get("cach_chia") == "tach":
        return [{**chung, "doi_tuong": p} for p in phan]
    return [{**chung, "doi_tuong": "+".join(phan)}]


def xem_truoc(d: dict) -> dict:
    ke_hoach = [fb.dung_ke_hoach(r) for r in form_sang_dong(d)]
    ra = []
    for kh in ke_hoach:
        bd = kh["adsets"][0].get("start_time")
        ra.append({
            "chien_dich": kh["campaign"]["name"],
            "tai_khoan": next(k for k, v in fb.TAI_KHOAN.items() if v == kh["account"]),
            "post": kh["ad"]["creative"]["object_story_id"],
            "bat_dau": datetime.strptime(bd[:16], "%Y-%m-%dT%H:%M").strftime("%H:%M %d/%m/%Y") if bd else "ngay khi bật",
            "nhom": [{"ten": n["name"], "ngan_sach": n["daily_budget"],
                      "chi_tiet": fb.chi_tiet_nham_vao(n["targeting"])} for n in kh["adsets"]],
            "canh_bao": kh["canh_bao"],
        })
    tong = sum(n["ngan_sach"] for c in ra for n in c["nhom"])
    return {"chien_dich": ra, "tong_ngan_sach": tong}, ke_hoach


def tao(d: dict) -> dict:
    _, ke_hoach = xem_truoc(d)
    try:
        fb.kiem_tra_quyen()
    except SystemExit as e:
        raise ValueError(str(e)) from None
    ket_qua = []
    for kh in ke_hoach:
        try:
            r = fb.tao(kh)
            link = (f"https://adsmanager.facebook.com/adsmanager/manage/campaigns?act={kh['account']}"
                    f"&selected_campaign_ids={r['campaign']}")
            ket_qua.append({"ok": True, "chien_dich": kh["campaign"]["name"], "id": r["campaign"],
                            "so_nhom": len(r["adsets"]), "so_qc": len(r["ads"]), "link": link})
            ghi_nhat_ky(kh, r)
        except RuntimeError as e:
            ket_qua.append({"ok": False, "chien_dich": kh["campaign"]["name"], "loi": str(e)})
    return {"ket_qua": ket_qua}


def ghi_nhat_ky(kh: dict, r: dict) -> None:
    moi = not NHAT_KY.exists()
    NHAT_KY.parent.mkdir(parents=True, exist_ok=True)
    with open(NHAT_KY, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if moi:
            w.writerow(["thoi_gian", "tai_khoan", "campaign_id", "chien_dich", "nhom", "ngan_sach_ngay", "post"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), kh["account"], r["campaign"], kh["campaign"]["name"],
                    " || ".join(n["name"] for n in kh["adsets"]), sum(n["daily_budget"] for n in kh["adsets"]),
                    kh["ad"]["creative"]["object_story_id"]])


class XuLy(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{datetime.now():%H:%M:%S}] {fmt % args}\n")

    def _tra(self, code: int, body, loai="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", loai)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _chan(self) -> bool:
        # Host lạ = trang web khác trỏ tên miền của nó về 127.0.0.1 (DNS rebinding) — header riêng không chặn được kiểu này
        if self.headers.get("Host", "") not in (f"localhost:{CONG}", f"127.0.0.1:{CONG}"):
            self._tra(403, {"loi": "Host không hợp lệ."})
            return True
        if self.headers.get(HEADER_BAT_BUOC) != "1":
            self._tra(403, {"loi": "Thiếu header — chỉ gọi từ form."})
            return True
        return False

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._tra(200, TRANG.read_bytes(), "text/html; charset=utf-8")
        if self._chan():
            return
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/cau-hinh":
                return self._tra(200, cau_hinh())
            if u.path == "/api/san-pham":
                return self._tra(200, fb_bai_dang.tim_san_pham(q.get("q", "")))
            if u.path == "/api/bai-dang":
                return self._tra(200, fb_bai_dang.tim_bai_dang([q.get("ma", ""), q.get("ten", "")]))
            return self._tra(404, {"loi": "Không có"})
        except Exception as e:  # noqa: BLE001 — báo lỗi ra form thay vì sập server
            traceback.print_exc()
            return self._tra(500, {"loi": fb.an_bi_mat(e)})

    def do_POST(self):
        if self._chan():
            return
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if self.path == "/api/xem-truoc":
                return self._tra(200, xem_truoc(d)[0])
            if self.path == "/api/tao":
                return self._tra(200, tao(d))
            return self._tra(404, {"loi": "Không có"})
        except (ValueError, KeyError) as e:
            return self._tra(400, {"loi": str(e)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._tra(500, {"loi": fb.an_bi_mat(e)})


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--khong-mo", action="store_true", help="Không tự mở trình duyệt")
    args = ap.parse_args()
    sv = ThreadingHTTPServer(("127.0.0.1", CONG), XuLy)
    url = f"http://localhost:{CONG}/"
    print(f"Form lên chiến dịch: {url}  (Ctrl+C để tắt)")
    if not args.khong_mo:
        webbrowser.open(url)
    try:
        sv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
