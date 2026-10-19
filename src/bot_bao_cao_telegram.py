"""Bot Telegram trả báo cáo ads theo lệnh gõ trong nhóm "Ads L'amme" (bot @lamme01_bot).

Lệnh (gõ trong nhóm, hoặc bấm nút "/" của Telegram):
    /baocao        kết quả hôm nay, tính đến lúc gõ
    /homqua        kết quả cả ngày hôm qua
    /tuan          7 ngày qua (không tính hôm nay)
    /thang         tháng này, từ ngày 1 tới lúc gõ
    /doanhthuthangtruoc  doanh thu Nhanh.vn theo nhân viên cả tháng trước (lấy lần đầu ~2–3 phút, lưu 6 giờ)
    /doanhthucomthangnay | /doanhthucomthangtruoc  doanh thu Nhanh.vn theo trạng thái: 3 nhân viên, Shopee, TikTok Shop,
                   bán lẻ cửa hàng + tổng các kênh (thành công / đang gửi / hoàn / hủy), tháng này từ ngày 1 tới lúc gõ hoặc cả tháng trước
    /nhanvien      doanh thu Nhanh.vn theo nhân viên (mặc định tháng trước; /nhanvien homnay|homqua|thang|thangtruoc)
    /san           doanh thu Shopee + TikTok Shop trên Nhanh (mặc định hôm nay; /san homqua|thang|thangtruoc)
    /ngay 14       N ngày qua (1–90)
    /tinnhan       hội thoại bắt đầu từ QC chia theo nhân viên trả lời trên Pancake (src/pancake_tin_nhan.py);
                   mặc định hôm nay, /tinnhan homqua, /tinnhan 03/10 (trong 30 ngày), /tinnhan thang, /tinnhan
                   thangtruoc — 1 ngày mất 2–5 phút; tháng cộng các ngày đã lưu (lịch \\LAMME\\TinNhanPancake tính sẵn)
    /chotdon       đơn + doanh số sale đã chốt, đọc từ tin xác nhận đơn trong hội thoại Pancake (src/pancake_chot_don.py);
                   mặc định hôm nay, /chotdon homqua, /chotdon 03/10 (trong 30 ngày); thêm "chitiet" để liệt kê từng đơn
    /topsp         top 10 sản phẩm cha theo kênh: 3 NV online, Shopee, TikTok Shop, cửa hàng + tồn kho tổng (src/top_sp_nhan_vien.py): /topsp (tháng này) | homnay |
                   homqua | thangtruoc
    /ngansachhomnay  ngân sách ads đã setup cho hôm nay (src/ngan_sach_hom_nay.py; lịch 7h \\LAMME\\NganSach_07h);
                   /ngansachhomnay chitiet liệt kê đủ mọi chiến dịch
    /baocaotaichinh  như /baocao + giá vốn, phí sàn, CP QC sàn → lãi sau 3 khoản (bc.soan_tai_chinh);
                   mặc định hôm nay, /baocaotaichinh homqua | 7ngay | thang | thangtruoc — riêng thang/thangtruoc
                   bot hỏi thêm làm báo cáo HTML: /html (trong 10 phút) → gửi tệp .html, /khonghtml bỏ qua
    /offchiphisan  tạm dừng tự cập nhật CP QC sàn (lịch 60 phút/lần trong phiên Claude) · /onchiphisan bật lại
    /top           thêm top 10 chiến dịch chi nhiều nhất vào báo cáo hôm nay (vd: /top homqua, /top thang)
    /nhan          đề xuất nhân nhóm (src/de_xuat_nhan_nhom.py): hôm nay chi phí/mua < 100k và chi phí/tin < 30k
    /nhanban 1,2,3 nhân các nhóm số 1, 2, 3 của tin đề xuất (trả lời đúng tin; không thì lấy tin đề xuất mới nhất)
                   "x3" ở cuối = mỗi nhóm nhân thành 3 nhóm (/nhanban 1,2 x3); riêng từng nhóm: /nhanban 1x3,2x2,6
                   → bot hỏi ngân sách → /ngansach 150000 (hoặc 150k,200k theo thứ tự, hoặc "giu") → /ok trong 1 phút
                   thì mới nhân (src/nhan_nhom.py: bản sao TẮT, tên "… - Nhân dd/mm"). /huy để huỷ.
                   Nhân xong bot hỏi bật: /bat (tất cả) | /bat 1,3 | /khongbat — trong 10 phút.
    /canhbao       nhóm mới (tạo ≤3 ngày, đang chạy) đã chi ≥ 40k mà 0 tin nhắn, kèm CPC + CPM (src/canh_bao_nhom_moi.py;
                   lịch \\LAMME\\CanhBaoNhomMoi tự báo 8h, 11h, 14h, 17h, 20h) → trả lời tin: /tat 1,2 (tắt nhóm) | /giu 1,2 | /tat
    /help          danh sách lệnh

Chỉ trả lời trong nhóm TELEGRAM_CHAT_ID (config/.env) — tin ở chat khác bị bỏ qua. Nghe bằng long-polling
(getUpdates), không cần mở cổng. Chạy nền bằng lịch Windows `\\LAMME\\BotBaoCaoAds` (khởi động cùng máy, tự
bật lại nếu tắt); log ở data/bot_bao_cao.log. Lệnh gõ lúc máy tắt quá 10 phút thì bỏ qua, không trả bù.

    python src/bot_bao_cao_telegram.py              # chạy bot (Ctrl+C để dừng)
    python src/bot_bao_cao_telegram.py --dang-ky    # đăng ký menu lệnh với Telegram rồi thoát
"""
import os
import re
import socket
import sys
import time
import traceback
from datetime import datetime, timedelta

import requests

import bao_cao_ads_telegram as bc
import de_xuat_nhan_nhom
import bao_cao_tai_chinh_html
import canh_bao_nhom_moi
import cp_qc_san
import doanh_thu_nv_trang_thai
import fb_ads_create as fb
import nhan_nhom
import ngan_sach_hom_nay
import pancake_chot_don
import pancake_tin_nhan
import top_sp_nhan_vien

TOK = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()
API = f"https://api.telegram.org/bot{TOK}"
CU_QUA = 600          # giây — lệnh cũ hơn thế (máy tắt lúc gõ) thì bỏ qua
CONG_KHOA = 47651     # chiếm cổng này để chỉ chạy 1 bản bot
NGHI = 60             # giây — cùng 1 lệnh (cùng tham số) gõ lại trong khoảng này thì không chạy lại (tránh dồn gọi Meta)
HAN_NGAN_SACH = 600   # giây — chờ người dùng cho ngân sách sau /nhanban
HAN_OK = 60           # giây — chờ /ok sau khi chốt ngân sách (chủ trang yêu cầu 1 phút)
LENH_NHAN = ("nhanban", "ngansach", "ok", "huy", "bat", "khongbat", "tat", "giu", "html", "khonghtml")   # hội thoại — không áp NGHI
HAN_BAT = 600         # giây — sau khi nhân xong, chờ /bat để bật các nhóm vừa nhân (chủ trang yêu cầu 04/10/2026)
LENH_LAU = ("doanhthucomthangnay", "doanhthucomthangtruoc", "doanhthucomthantruoc", "doanhthuthangtruoc", "nhanvien", "san", "thang", "thangnay", "tuan", "ngay", "tinnhan", "chotdon", "canhbao", "ngansachhomnay", "topsp", "baocaotaichinh")   # gửi "đang lấy số liệu" trước

LENH = [
    ("baocao", "Kết quả hôm nay (tính đến lúc gõ)"),
    ("homqua", "Kết quả cả ngày hôm qua"),
    ("baocaotaichinh", "Báo cáo tài chính: doanh thu, giá vốn, phí sàn, CP QC, lãi — /baocaotaichinh | homqua | thang"),
    ("tuan", "7 ngày qua"),
    ("thang", "Tháng này, từ ngày 1 tới lúc gõ"),
    ("doanhthuthangtruoc", "Doanh thu Nhanh.vn theo nhân viên tháng trước"),
    ("doanhthucomthangnay", "Doanh thu theo trạng thái: nhân viên, Shopee, TikTok, cửa hàng — tháng này"),
    ("doanhthucomthangtruoc", "Doanh thu theo trạng thái: nhân viên, Shopee, TikTok, cửa hàng — tháng trước"),
    ("nhanvien", "Doanh thu Nhanh.vn theo nhân viên: /nhanvien homnay|homqua|thang|thangtruoc"),
    ("topsp", "Top 10 sản phẩm cha theo kênh + tồn kho tổng: /topsp (tháng này) | thangtruoc | 7ngay | homnay | homqua"),
    ("san", "Doanh thu Shopee + TikTok Shop: /san (hôm nay) | homqua | thang | thangtruoc"),
    ("ngay", "N ngày qua, vd: /ngay 14"),
    ("tinnhan", "Hội thoại từ QC theo nhân viên trả lời (Pancake): /tinnhan | homqua | 03/10 | thang | thangtruoc"),
    ("chotdon", "Đơn + doanh số sale chốt trong hội thoại Pancake: /chotdon | homqua | 03/10 (thêm chitiet)"),
    ("top", "Thêm top 10 chiến dịch, vd: /top, /top homqua, /top thang"),
    ("nhan", "Đề xuất nhân nhóm: hôm nay chi phí/mua < 100k và /tin nhắn < 30k"),
    ("nhanban", "Nhân nhóm trong tin đề xuất, vd: /nhanban 1,2,3 hoặc /nhanban 1,2 x3 (mỗi nhóm thành 3)"),
    ("ngansach", "Ngân sách/ngày cho nhóm nhân, vd: /ngansach 150000 hoặc giu"),
    ("ok", "Xác nhận nhân (trong 1 phút)"),
    ("huy", "Huỷ lệnh nhân đang chờ"),
    ("bat", "Bật nhóm vừa nhân: /bat (tất cả) hoặc /bat 1,3"),
    ("khongbat", "Không bật nhóm vừa nhân (để TẮT)"),
    ("ngansachhomnay", "Ngân sách ads đã setup cho hôm nay (thêm chitiet: đủ mọi chiến dịch)"),
    ("html", "Gửi báo cáo tài chính tháng dạng tệp HTML (sau /baocaotaichinh thang|thangtruoc)"),
    ("offchiphisan", "Tạm dừng tự cập nhật chi phí quảng cáo Shopee/TikTok"),
    ("onchiphisan", "Bật lại tự cập nhật chi phí quảng cáo Shopee/TikTok"),
    ("canhbao", "Nhóm mới: chi ≥ 40k mà 0 tin nhắn, hoặc giá tin > 60k mà 0 mua (kèm CPC, CPM)"),
    ("tat", "Tắt nhóm trong tin cảnh báo: /tat 1,2 hoặc /tat (tất cả)"),
    ("giu", "Giữ nhóm trong tin cảnh báo chạy tiếp: /giu 1,2"),
    ("help", "Danh sách lệnh"),
]
# mô tả có dấu "<" (vd "chi phí/mua < 100k") → phải escape, không thì Telegram từ chối cả tin /help (lỗi từ 03/10)
TRO_GIUP = "<b>Lệnh báo cáo ads</b>\n" + "\n".join(f"/{k} — {bc.html.escape(m)}" for k, m in LENH)


def log(s: str) -> None:
    print(f"[{datetime.now():%d/%m %H:%M:%S}] {s}", flush=True)


def tra_loi_anh(anh: bytes, chu_thich: str, reply_to: int | None = None) -> int | None:
    """Gửi ảnh PNG vào nhóm (sendPhoto); lỗi thì trả None để gửi bản chữ thay thế."""
    data = {"chat_id": CHAT, "caption": chu_thich[:1000], "parse_mode": "HTML"}
    if reply_to:
        data["reply_to_message_id"] = reply_to
        data["allow_sending_without_reply"] = True
    try:
        r = requests.post(f"{API}/sendPhoto", data=data, files={"photo": ("top_sp.png", anh, "image/png")},
                          timeout=60).json()
    except requests.RequestException as e:
        log(f"gửi ảnh lỗi: {type(e).__name__}")
        return None
    if not r.get("ok"):
        log(f"gửi ảnh lỗi: {r}")
        return None
    return r["result"]["message_id"]


def tra_loi(text: str, reply_to: int | None = None) -> int | None:
    """Gửi vào nhóm; trả về message_id tin đầu."""
    mid = None
    for i, phan in enumerate(bc.chia_tin(text)):
        data = {"chat_id": CHAT, "text": phan, "parse_mode": "HTML", "disable_web_page_preview": True}
        if reply_to and i == 0:
            data["reply_to_message_id"] = reply_to
            data["allow_sending_without_reply"] = True
        r = requests.post(f"{API}/sendMessage", data=data, timeout=30).json()
        if not r.get("ok"):
            log(f"gửi lỗi: {r}")
        elif i == 0:
            mid = r["result"]["message_id"]
    return mid


def bao_cao(ngay: str, top: int = 0) -> str:
    bc.TOP = top
    tu, den, nhan = bc.khoang_ngay(ngay)
    nh = bc.so_lieu_nhanh(tu, den)
    return bc.soan_tin(bc.lay_so_lieu(tu, den), nhan, nh["nv"], nh["san"], nh["ban_le"], bc.cp_qc_san(tu, den))


def xu_ly(lenh: str, doi: str) -> str | None:
    """Lệnh → nội dung trả lời (None = không phải lệnh của bot)."""
    doi = doi.strip().lower()
    if lenh in ("baocao", "homnay"):
        return bao_cao("hom-nay")
    if lenh == "homqua":
        return bao_cao("hom-qua")
    if lenh == "tuan":
        return bao_cao("7")
    if lenh in ("thang", "thangnay"):
        return bao_cao("thang-nay")
    if lenh == "san":
        ngay = {"": "hom-nay", "homnay": "hom-nay", "homqua": "hom-qua", "thang": "thang-nay", "thangnay": "thang-nay",
                "thangtruoc": "thang-truoc"}.get(doi.replace(" ", ""))
        if ngay is None:
            return "Dùng: <code>/san</code> (hôm nay), <code>/san homqua</code>, <code>/san thang</code>, <code>/san thangtruoc</code>"
        tu, den, nhan = bc.khoang_ngay(ngay)
        return bc.soan_san(bc.so_lieu_nhanh_cache(tu, den)["san"], nhan, bc.cp_qc_san(tu, den), bc.hang_muc_san(tu, den))
    if lenh in ("doanhthucomthangnay", "doanhthucomthangtruoc", "doanhthucomthantruoc"):
        tu, den, nhan = bc.khoang_ngay("thang-nay" if lenh.endswith("thangnay") else "thang-truoc")
        return doanh_thu_nv_trang_thai.soan_tin(doanh_thu_nv_trang_thai.theo_trang_thai_cache(tu, den), nhan)
    if lenh in ("doanhthuthangtruoc", "nhanvien"):
        ngay = {"": "thang-truoc", "thangtruoc": "thang-truoc", "thang": "thang-nay", "thangnay": "thang-nay",
                "homnay": "hom-nay", "homqua": "hom-qua"}.get("" if lenh == "doanhthuthangtruoc" else doi.replace(" ", ""))
        if ngay is None:
            return "Dùng: <code>/nhanvien</code> (tháng trước), <code>/nhanvien thang</code>, <code>homnay</code>, <code>homqua</code>"
        tu, den, nhan = bc.khoang_ngay(ngay)
        nh = bc.so_lieu_nhanh_cache(tu, den)
        return bc.soan_nhan_vien(nh["nv"], nhan, nh["ban_le"], nh["san"])
    if lenh == "ngay":
        m = re.fullmatch(r"(\d{1,2})", doi)
        if not m or not 1 <= int(m.group(1)) <= 90:
            return "Gõ số ngày từ 1 đến 90, vd: <code>/ngay 14</code>"
        return bao_cao(m.group(1))
    if lenh == "tinnhan":
        h = datetime.now().date()
        doi = doi.replace(" ", "")
        try:
            if doi in ("thang", "thangnay", "thangtruoc"):
                tu, den, nhan = bc.khoang_ngay("thang-truoc" if doi == "thangtruoc" else "thang-nay")
                return pancake_tin_nhan.bao_cao(datetime.fromisoformat(tu).date(), datetime.fromisoformat(den).date(), nhan)
        except pancake_tin_nhan.DangTinh as e:
            return str(e)
        if doi in ("", "homnay"):
            ngay, nhan = h, f"hôm nay {h:%d/%m} (đến {datetime.now():%H:%M})"
        elif doi == "homqua":
            ngay = h - timedelta(days=1)
            nhan = f"hôm qua {ngay:%d/%m}"
        else:
            m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})", doi)
            try:
                ngay = datetime(h.year, int(m.group(2)), int(m.group(1))).date() if m else None
            except ValueError:
                ngay = None
            if ngay and ngay > h:
                ngay = ngay.replace(year=h.year - 1)
            if not ngay or (h - ngay).days > 30:
                return ("Dùng: <code>/tinnhan</code> (hôm nay), <code>/tinnhan homqua</code>, <code>/tinnhan 03/10</code> "
                        "(trong 30 ngày), <code>/tinnhan thang</code>, <code>/tinnhan thangtruoc</code>")
            nhan = f"ngày {ngay:%d/%m}"
        return pancake_tin_nhan.bao_cao(ngay, ngay, nhan)
    if lenh == "chotdon":
        h = datetime.now().date()
        chi_tiet = "chitiet" in doi
        doi = doi.replace("chitiet", "").replace(" ", "")
        if doi in ("", "homnay"):
            ngay, nhan = h, f"hôm nay {h:%d/%m} (đến {datetime.now():%H:%M})"
        elif doi == "homqua":
            ngay = h - timedelta(days=1)
            nhan = f"hôm qua {ngay:%d/%m}"
        else:
            m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})", doi)
            try:
                ngay = datetime(h.year, int(m.group(2)), int(m.group(1))).date() if m else None
            except ValueError:
                ngay = None
            if ngay and ngay > h:
                ngay = ngay.replace(year=h.year - 1)
            if not ngay or (h - ngay).days > 30:
                return ("Dùng: <code>/chotdon</code> (hôm nay), <code>/chotdon homqua</code>, <code>/chotdon 03/10</code> "
                        "(trong 30 ngày); thêm <code>chitiet</code> để liệt kê từng đơn")
            nhan = f"ngày {ngay:%d/%m}"
        return pancake_chot_don.bao_cao(ngay, nhan, chi_tiet)
    if lenh == "top":
        ngay = {"": "hom-nay", "homnay": "hom-nay", "homqua": "hom-qua", "tuan": "7",
                "thang": "thang-nay"}.get(doi.replace(" ", ""))
        if ngay is None:
            return "Dùng: <code>/top</code>, <code>/top homqua</code>, <code>/top tuan</code> hoặc <code>/top thang</code>"
        return bao_cao(ngay, top=10)
    if lenh == "baocaotaichinh":
        ngay = {"": "hom-nay", "homnay": "hom-nay", "homqua": "hom-qua", "7ngay": "7", "tuan": "7",
                "thang": "thang-nay", "thangnay": "thang-nay", "thangtruoc": "thang-truoc"}.get(doi.replace(" ", ""))
        if ngay is None:
            return ("Dùng: <code>/baocaotaichinh</code> (hôm nay), <code>homqua</code>, <code>7ngay</code>, "
                    "<code>thang</code>, <code>thangtruoc</code>")
        tu, den, nhan = bc.khoang_ngay(ngay)
        nh = bc.so_lieu_nhanh_cache(tu, den)
        rows, cp = bc.lay_so_lieu(tu, den), bc.cp_qc_san(tu, den)
        tin = bc.soan_tai_chinh(rows, nhan, nh["nv"], nh["san"], nh["ban_le"], cp)
        if ngay in ("thang-nay", "thang-truoc"):   # báo cáo tháng: hỏi làm thêm bản HTML (chủ trang yêu cầu 06/10/2026)
            CHO_HTML.clear()
            CHO_HTML.update({"han": time.time() + HAN_HTML, "nhan": nhan, "tu": tu, "den": den,
                             "rows": rows, "nh": nh, "cp": cp})
            tin += ("\n\n❓ <b>Có làm báo cáo HTML không?</b> <code>/html</code> — gửi tệp báo cáo (mở bằng trình duyệt) · "
                    "<code>/khonghtml</code> — thôi (trong 10 phút)")
        return tin
    if lenh in ("offchiphisan", "onchiphisan"):   # chủ trang thêm 06/10/2026
        if lenh == "offchiphisan":
            cp_qc_san.dat_tam_dung(True, AI_GO)
            return ("⏸ Đã <b>tạm dừng</b> tự cập nhật chi phí quảng cáo Shopee/TikTok. Báo cáo vẫn hiện số đã có, kèm giờ "
                    "cập nhật cuối. Gõ <code>/onchiphisan</code> để bật lại.")
        td = cp_qc_san.tam_dung()
        cp_qc_san.dat_tam_dung(False)
        return ("▶️ Đã <b>bật lại</b> tự cập nhật chi phí quảng cáo sàn (60 phút/lần, phút 45, 8h–23h)."
                if td else "Tự cập nhật chi phí quảng cáo sàn đang bật sẵn (60 phút/lần, phút 45, 8h–23h).")
    if lenh == "topsp":
        ngay = {"": "thang-nay", "thang": "thang-nay", "thangnay": "thang-nay", "thangtruoc": "thang-truoc",
                "7ngay": "7", "7": "7", "tuan": "7", "homnay": "hom-nay", "homqua": "hom-qua"}.get(doi.replace(" ", ""))
        if ngay is None:
            return ("Dùng: <code>/topsp</code> (tháng này), <code>/topsp thangtruoc</code>, <code>/topsp 7ngay</code>, "
                    "<code>/topsp homnay</code>, <code>/topsp homqua</code>")
        tu, den, nhan = bc.khoang_ngay(ngay)
        # gửi ẢNH bảng (Telegram không hiển thị bảng HTML) — chủ trang yêu cầu 06/10/2026
        return top_sp_nhan_vien.bao_cao_anh(top_sp_nhan_vien.theo_san_pham_cache(tu, den), nhan)
    if lenh == "ngansachhomnay":
        return ngan_sach_hom_nay.bao_cao(chi_tiet=doi.replace(" ", "") in ("chitiet", "chitiết", "full"))
    if lenh == "canhbao":
        global DS_CANH_BAO
        DS_CANH_BAO = canh_bao_nhom_moi.nhom_cham_nguong()
        return canh_bao_nhom_moi.soan(DS_CANH_BAO, "Kiểm tra nhóm quảng cáo mới")
    if lenh == "nhan":
        global DS_CHO_LUU
        tin, DS_CHO_LUU = de_xuat_nhan_nhom.bao_cao()
        return tin
    if lenh in ("help", "start", "lenh"):
        return TRO_GIUP
    return None


# ---------------------------------------------------------------- nhân nhóm (hội thoại 3 bước)
AI_GO = ""                             # tên người gõ lệnh đang xử lý (ghi vào cờ tạm dừng)
DS_CHO_LUU: list[dict] | None = None   # danh sách của /nhan vừa soạn — lưu kèm message_id sau khi gửi
DS_CANH_BAO: list[dict] | None = None  # danh sách của /canhbao vừa soạn — như trên, cho /tat, /giu
CHO: dict = {}                         # lệnh nhân đang chờ: {"nhom": [...], "ngan_sach": [...], "buoc", "han"}
CHO_BAT: dict = {}                     # nhóm vừa nhân chờ bật: {"moi": [{"id","ten","acc"}], "han"}
CHO_HTML: dict = {}                    # báo cáo tài chính tháng chờ /html: {"han", "nhan", "tu", "den", "rows", "nh", "cp"}
HAN_HTML = 600


def xu_ly_html(lenh: str) -> str | dict:
    """/html → {"tep": bytes, "ten": tên tệp, "chu_thich"}; /khonghtml → bỏ."""
    if not CHO_HTML or time.time() > CHO_HTML["han"]:
        CHO_HTML.clear()
        return "Không có báo cáo tài chính tháng nào đang chờ — gõ <code>/baocaotaichinh thang</code> hoặc <code>thangtruoc</code> trước."
    if lenh == "khonghtml":
        CHO_HTML.clear()
        return "Ok, không làm báo cáo HTML."
    c = dict(CHO_HTML)
    CHO_HTML.clear()
    try:   # kèm top 10 sản phẩm cha tổng các kênh; lỗi thì vẫn gửi phần tài chính
        top = top_sp_nhan_vien.du_lieu(top_sp_nhan_vien.theo_san_pham_cache(c["tu"], c["den"]))
    except Exception:  # noqa: BLE001
        log(fb.an_bi_mat(traceback.format_exc()))
        top = None
    noi_dung = bao_cao_tai_chinh_html.tao_html(c["nhan"], c["rows"], c["nh"], c["cp"], top,
                                               bc.hang_muc_san(c["tu"], c["den"]))
    return {"tep": noi_dung.encode("utf-8"), "ten": f"bao-cao-tai-chinh_{c['tu']}_{c['den']}.html",
            "chu_thich": f"📑 Báo cáo tài chính — {bc.html.escape(c['nhan'])} (mở tệp bằng trình duyệt)"}


def tra_loi_tep(noi_dung: bytes, ten: str, chu_thich: str, reply_to: int | None = None) -> int | None:
    data = {"chat_id": CHAT, "caption": chu_thich[:1000], "parse_mode": "HTML"}
    if reply_to:
        data["reply_to_message_id"] = reply_to
        data["allow_sending_without_reply"] = True
    try:
        r = requests.post(f"{API}/sendDocument", data=data, files={"document": (ten, noi_dung, "text/html")},
                          timeout=60).json()
    except requests.RequestException as e:
        log(f"gửi tệp lỗi: {type(e).__name__}")
        return None
    if not r.get("ok"):
        log(f"gửi tệp lỗi: {r}")
        return None
    return r["result"]["message_id"]


def _so_tien(s: str) -> int:
    s = s.strip().lower().replace(".", "").replace(",", "")
    he_so = 1000 if s.endswith("k") else 1
    return int(float(s.rstrip("k")) * he_so)


def _dong_nhom(i: int, n: dict, ns: int | None) -> str:
    hien = bc.vnd(n["ns_goc"]) + "/ngày" if n["ns_goc"] else "theo chiến dịch (CBO)"
    moi = "" if ns is None else f" → <b>{bc.vnd(ns)}/ngày</b>" + (" mỗi nhóm" if n["sl"] > 1 else "")
    sl = f" <b>× {n['sl']} nhóm</b>" if n["sl"] > 1 else ""
    return f"{i}. {bc.html.escape(n['nhom'])} ({n['tk']}){sl} — đang {hien}{moi}"


def _doc_nhanban(doi: str) -> list[tuple[int, int]]:
    """'1,2,3' → [(1,1),(2,1),(3,1)]; '1,2 x3' → mỗi nhóm 3 bản; '1x3,2x2,6' → riêng từng nhóm."""
    doi = doi.lower().replace("×", "x").replace("*", "x")
    chung = 1
    m = re.search(r"(?:^|\s)x\s*(\d+)\s*(?:nhóm|nhom)?\s*$", doi)
    if m:
        chung, doi = int(m.group(1)), doi[:m.start()]
    return [(int(a), int(b) if b else chung) for a, b in re.findall(r"(\d+)(?:\s*x\s*(\d+))?", doi)]


def xu_ly_canh_bao(lenh: str, doi: str, tra_loi_tin: int | None) -> str:
    """/tat 1,2 | /giu 1,2 trên tin cảnh báo nhóm mới (trả lời đúng tin; không thì tin cảnh báo mới nhất)."""
    d = canh_bao_nhom_moi.doc_ds(tra_loi_tin)
    if not d or not d["nhom"]:
        return "Chưa có tin cảnh báo nhóm mới nào để tắt/giữ — gõ /canhbao để kiểm tra."
    ds = d["nhom"]
    so = [int(x) for x in re.findall(r"\d+", doi)] or list(range(1, len(ds) + 1))
    sai = [x for x in so if not 1 <= x <= len(ds)]
    if sai:
        return f"Tin cảnh báo lúc {d['luc']} chỉ có số 1 đến {len(ds)} — số {', '.join(map(str, sai))} không có."
    chon = [(x, ds[x - 1]) for x in dict.fromkeys(so)]
    if lenh == "giu":
        canh_bao_nhom_moi.ghi_giu([n["id"] for _, n in chon])
        return "✅ Giữ chạy: " + ", ".join(f"#{x} {bc.html.escape(n['nhom'])}" for x, n in chon)
    dong = [f"<b>Tắt nhóm (tin cảnh báo lúc {d['luc']}):</b>"]
    for x, n in chon:
        try:
            fb._goi("POST", n["id"], {"status": "PAUSED"})
            dong.append(f"⏸ #{x} {bc.html.escape(n['nhom'])} — đã TẮT")
            log(f"tắt nhóm {n['id']}")
        except Exception as e:  # noqa: BLE001
            log(fb.an_bi_mat(traceback.format_exc()))
            dong.append(f"✗ #{x} {bc.html.escape(n['nhom'])} — {bc.html.escape(fb.an_bi_mat(e))[:200]}")
    return "\n".join(dong)


def xu_ly_nhan(lenh: str, doi: str, tra_loi_tin: int | None) -> str:
    doi = doi.strip()
    if lenh == "huy":
        CHO.clear()
        return "Đã huỷ lệnh nhân nhóm."
    if lenh in ("bat", "khongbat"):
        if not CHO_BAT or time.time() > CHO_BAT["han"]:
            CHO_BAT.clear()
            return "Không có nhóm vừa nhân nào đang chờ bật (quá 10 phút thì bật tay trên Ads Manager)."
        moi = CHO_BAT["moi"]
        if lenh == "khongbat":
            CHO_BAT.clear()
            return f"Ok — {len(moi)} nhóm vừa nhân vẫn để TẮT."
        so = [int(x) for x in re.findall(r"\d+", doi)] or list(range(1, len(moi) + 1))
        sai = [x for x in so if not 1 <= x <= len(moi)]
        if sai:
            return f"Chỉ có nhóm #1 đến #{len(moi)} — số {', '.join(map(str, sai))} không có."
        dong = ["<b>Bật nhóm vừa nhân:</b>"]
        for x in dict.fromkeys(so):
            m = moi[x - 1]
            try:
                fb._goi("POST", m["id"], {"status": "ACTIVE"})
                dong.append(f"🟢 #{x} <a href=\"{nhan_nhom.link_nhom(m['acc'], m['id'])}\">{bc.html.escape(m['ten'])}</a> — đã BẬT")
                log(f"bật nhóm {m['id']}")
            except Exception as e:  # noqa: BLE001
                log(fb.an_bi_mat(traceback.format_exc()))
                dong.append(f"✗ #{x} {bc.html.escape(m['ten'])} — {bc.html.escape(fb.an_bi_mat(e))[:200]}")
        con = [i + 1 for i in range(len(moi)) if i + 1 not in so]
        if con:
            CHO_BAT["moi"] = moi  # còn nhóm chưa bật → vẫn cho /bat tiếp trong thời hạn cũ
            dong.append(f"Còn TẮT: #{', #'.join(map(str, con))} — gõ /bat {','.join(map(str, con))} nếu muốn bật nốt.")
        else:
            CHO_BAT.clear()
        dong.append("Lưu ý: nhóm chỉ chạy khi chiến dịch chứa nó cũng đang bật.")
        return "\n".join(dong)
    if lenh == "nhanban":
        chon = _doc_nhanban(doi)
        if not chon:
            return ("Gõ số thứ tự trong tin đề xuất, vd: <code>/nhanban 1,2,3</code>, <code>/nhanban 1,2 x3</code> "
                    "(mỗi nhóm thành 3) — trả lời đúng tin đề xuất.")
        sl_theo_so = {}
        for x, k in chon:
            sl_theo_so[x] = k  # gõ trùng số → lấy lần sau cùng
        so = list(sl_theo_so)
        ds = de_xuat_nhan_nhom.doc_ds(tra_loi_tin)
        if not ds or not ds["nhom"]:
            return "Chưa có tin đề xuất nào — gõ /nhan trước."
        sai = [x for x in so if not 1 <= x <= len(ds["nhom"])]
        if sai:
            return f"Tin đề xuất lúc {ds['luc']} chỉ có {len(ds['nhom'])} nhóm — số {', '.join(map(str, sai))} không có."
        if len(so) > nhan_nhom.TOI_DA_SO_NHOM:
            return f"Mỗi lần nhân tối đa {nhan_nhom.TOI_DA_SO_NHOM} nhóm gốc."
        if any(not 1 <= k <= nhan_nhom.TOI_DA_BAN_SAO for k in sl_theo_so.values()):
            return f"Mỗi nhóm nhân thành 1 đến {nhan_nhom.TOI_DA_BAN_SAO} nhóm."
        if sum(sl_theo_so.values()) > nhan_nhom.TOI_DA_TONG_BAN:
            return f"Mỗi lần tạo tối đa {nhan_nhom.TOI_DA_TONG_BAN} nhóm mới (đang chọn {sum(sl_theo_so.values())})."
        nhom = []
        for x in so:
            n = dict(ds["nhom"][x - 1])
            n["so"], n["sl"] = x, sl_theo_so[x]
            n["ns_goc"] = nhan_nhom.doc_nhom(n["id"])["ngan_sach"]
            nhom.append(n)
        CHO.clear()
        CHO.update({"nhom": nhom, "buoc": "ngan_sach", "han": time.time() + HAN_NGAN_SACH})
        tong_ban = sum(n["sl"] for n in nhom)
        return "\n".join([f"<b>Nhân {len(nhom)} nhóm → {tong_ban} nhóm mới</b> (từ tin đề xuất lúc {ds['luc']}):"]
                         + [_dong_nhom(n["so"], n, None) for n in nhom]
                         + ["", "Ngân sách/ngày cho nhóm nhân bao nhiêu?",
                            "<code>/ngansach 150000</code> — cùng 1 mức cho mỗi nhóm mới",
                            "<code>/ngansach 150k,200k,…</code> — theo đúng thứ tự trên",
                            "<code>/ngansach giu</code> — giữ như nhóm gốc · /huy để huỷ"])
    if not CHO or time.time() > CHO["han"]:
        CHO.clear()
        return "Không có lệnh nhân nào đang chờ (hoặc đã quá hạn) — gõ lại <code>/nhanban 1,2,3</code>."
    nhom = CHO["nhom"]
    if lenh == "ngansach":
        if doi.lower() in ("giu", "giữ"):
            ns = [None] * len(nhom)
        else:
            try:
                ns = [_so_tien(x) for x in re.split(r"[\s;/]+|,(?=\s*\d)", doi) if x.strip()]
            except ValueError:
                return "Không đọc được ngân sách — vd: <code>/ngansach 150000</code> hoặc <code>/ngansach 150k,200k</code>."
            if len(ns) == 1:
                ns = ns * len(nhom)
            if len(ns) != len(nhom):
                return f"Có {len(nhom)} nhóm nhưng gõ {len(ns)} mức ngân sách."
            if any(not 20_000 <= x <= nhan_nhom.TOI_DA_NGAN_SACH for x in ns):
                return f"Ngân sách mỗi nhóm phải từ 20.000đ đến {bc.vnd(nhan_nhom.TOI_DA_NGAN_SACH)}/ngày."
        ns = [None if n["ns_goc"] is None else x for n, x in zip(nhom, ns)]  # nhóm CBO: không đặt riêng
        tong = sum((x or n["ns_goc"] or 0) * n["sl"] for n, x in zip(nhom, ns))
        CHO.update({"ngan_sach": ns, "buoc": "ok", "han": time.time() + HAN_OK})
        nhieu = " (1), (2)…" if any(n["sl"] > 1 for n in nhom) else ""
        return "\n".join([f"<b>Sắp nhân</b> (nhóm mới để TẮT, tên thêm \" - Nhân {datetime.now():%d/%m}{nhieu}\"):"]
                         + [_dong_nhom(n["so"], n, x if x is not None else n["ns_goc"]) for n, x in zip(nhom, ns)]
                         + [f"Tổng thêm {bc.vnd(tong)}/ngày khi bật.", "",
                            "Gõ <b>/ok</b> trong 1 phút để nhân · /huy để huỷ"])
    if lenh == "ok":
        if CHO["buoc"] != "ok":
            return "Chưa chốt ngân sách — gõ <code>/ngansach 150000</code> (hoặc <code>giu</code>) trước."
        viec = [(n, x, k + 1 if n["sl"] > 1 else None) for n, x in zip(nhom, CHO["ngan_sach"]) for k in range(n["sl"])]
        CHO.clear()
        dong = [f"<b>Kết quả: {len(viec)} nhóm mới</b> (đang TẮT):"]
        moi = []
        for n, x, thu_tu in viec:
            try:
                r = nhan_nhom.nhan(n["id"], x, thu_tu)
                moi.append({"id": r["id"], "ten": r["ten"], "acc": r["acc"]})
                dong.append(f"✓ <b>#{len(moi)}</b> (từ số {n['so']}) <a href=\"{nhan_nhom.link_nhom(r['acc'], r['id'])}\">"
                            f"{bc.html.escape(r['ten'])}</a> · {r['so_qc']} quảng cáo"
                            + (f" · lỗi QC: {bc.html.escape(r['loi_qc'][0])}" if r["loi_qc"] else ""))
                log(f"nhân {n['id']} → {r['id']} ({x or 'giữ'} đ)")
            except Exception as e:  # noqa: BLE001 — 1 nhóm lỗi không chặn các nhóm khác
                log(fb.an_bi_mat(traceback.format_exc()))
                dong.append(f"✗ {n['so']}. {bc.html.escape(n['nhom'])} — {bc.html.escape(fb.an_bi_mat(e))[:200]}")
        if moi:
            CHO_BAT.clear()
            CHO_BAT.update({"moi": moi, "han": time.time() + HAN_BAT})
            dong += ["", "❓ <b>Bạn có muốn bật các nhóm vừa nhân không?</b>",
                     "<code>/bat</code> — bật tất cả · <code>/bat 1,3</code> — bật theo số # ở trên · "
                     "<code>/khongbat</code> — để TẮT (trong 10 phút)"]
        return "\n".join(dong)
    return ""


def dang_ky_menu() -> None:
    import json
    r = requests.post(f"{API}/setMyCommands", timeout=30, data={
        "commands": json.dumps([{"command": k, "description": m} for k, m in LENH], ensure_ascii=False),
        "scope": json.dumps({"type": "chat", "chat_id": int(CHAT)})}).json()
    print("Đăng ký menu lệnh:", "xong" if r.get("ok") else r)


def chay() -> None:
    try:
        khoa = socket.socket()
        khoa.bind(("127.0.0.1", CONG_KHOA))  # giữ tới khi thoát
    except OSError:
        log("Bot đã chạy ở tiến trình khác — thoát.")
        return
    while True:  # mất mạng / DNS lúc máy vừa bật: chờ rồi thử lại, không văng traceback (URL chứa token bot)
        try:
            me = requests.get(f"{API}/getMe", timeout=30).json()["result"]["username"].lower()
            break
        except (requests.RequestException, KeyError, ValueError) as e:
            log(f"chưa kết nối được Telegram ({type(e).__name__}) — thử lại sau 30s")
            time.sleep(30)
    log(f"Bot @{me} bắt đầu nghe lệnh trong chat {CHAT}.")
    offset = None
    vua_chay: dict[str, float] = {}   # "lệnh tham số" → lúc trả lời gần nhất
    while True:
        try:
            r = requests.get(f"{API}/getUpdates", timeout=70,
                             params={"timeout": 50, "offset": offset, "allowed_updates": '["message"]'}).json()
        except requests.RequestException as e:
            log(f"mất kết nối Telegram: {type(e).__name__} — thử lại sau 15s")
            time.sleep(15)
            continue
        if not r.get("ok"):
            log(f"getUpdates lỗi: {r}")
            time.sleep(30)
            continue
        for u in r["result"]:
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            text = (msg.get("text") or "").strip()
            m = re.match(r"^/([a-z_]+)(?:@(\w+))?\s*(.*)$", text, re.I | re.S)
            if not m or str(msg.get("chat", {}).get("id")) != CHAT:
                continue
            if m.group(2) and m.group(2).lower() != me:
                continue  # lệnh gửi cho bot khác trong nhóm
            if time.time() - msg.get("date", 0) > CU_QUA:
                log(f"bỏ lệnh cũ: {text}")
                continue
            lenh, ai = m.group(1).lower(), (msg.get("from") or {}).get("first_name", "?")
            global AI_GO
            AI_GO = ai
            log(f"{ai}: {text}")
            if lenh in LENH_NHAN:
                try:
                    tra = (msg.get("reply_to_message") or {}).get("message_id")
                    if lenh in ("html", "khonghtml"):
                        if lenh == "html" and CHO_HTML:
                            tra_loi("⏳ Đang tạo báo cáo HTML…", msg.get("message_id"))
                        tl = xu_ly_html(lenh)
                    else:
                        tl = (xu_ly_canh_bao if lenh in ("tat", "giu") else xu_ly_nhan)(lenh, m.group(3), tra)
                except Exception as e:  # noqa: BLE001
                    log(fb.an_bi_mat(traceback.format_exc()))
                    tl = f"Lỗi khi xử lý lệnh ({type(e).__name__}). Thử lại sau."
                if isinstance(tl, dict):
                    if tra_loi_tep(tl["tep"], tl["ten"], tl["chu_thich"], msg.get("message_id")) is None:
                        tra_loi("Gửi tệp HTML lỗi — thử lại /baocaotaichinh rồi /html.", msg.get("message_id"))
                else:
                    tra_loi(tl, msg.get("message_id"))
                continue
            khoa_lenh = f"{lenh} {m.group(3).strip().lower()}"
            if time.time() - vua_chay.get(khoa_lenh, 0) < NGHI:
                tra_loi("Vừa gửi báo cáo này xong — xem tin phía trên, hoặc gõ lại sau 1 phút.", msg.get("message_id"))
                continue
            if lenh in LENH_LAU:  # lấy cả tháng từ Nhanh mất 1–3 phút — báo trước cho người gõ khỏi tưởng bot treo
                tra_loi("⏳ Đang lấy số liệu, có thể mất 1–3 phút…", msg.get("message_id"))
            try:
                tl = xu_ly(lenh, m.group(3))
                vua_chay[khoa_lenh] = time.time()
            except Exception as e:  # noqa: BLE001 — báo lỗi vào nhóm, bot vẫn chạy tiếp
                # lỗi mạng của requests chứa URL kèm access_token → chỉ báo loại lỗi vào nhóm, chi tiết (đã che) vào log
                log(fb.an_bi_mat(traceback.format_exc()))
                tl = f"Không lấy được báo cáo ({type(e).__name__}). Thử lại sau ít phút."
            if tl:
                global DS_CHO_LUU, DS_CANH_BAO
                if isinstance(tl, dict):   # báo cáo dạng ảnh (/topsp): gửi ảnh, lỗi thì gửi bản chữ
                    mid = tra_loi_anh(tl["anh"], tl["chu_thich"], msg.get("message_id")) if tl.get("anh") else None
                    if mid is None:
                        mid = tra_loi(tl["tin"], msg.get("message_id"))
                else:
                    mid = tra_loi(tl, msg.get("message_id"))
                if DS_CANH_BAO is not None:  # /canhbao: nhớ số → nhóm cho /tat, /giu; đánh dấu đã báo
                    canh_bao_nhom_moi.luu_ds(DS_CANH_BAO, mid)
                    DS_CANH_BAO = None
                if DS_CHO_LUU is not None:  # /nhan: nhớ số thứ tự → nhóm, gắn với tin vừa gửi
                    de_xuat_nhan_nhom.luu_ds(DS_CHO_LUU, mid)
                    DS_CHO_LUU = None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if not TOK or not CHAT:
        raise SystemExit("Thiếu TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID trong config/.env.")
    if "--dang-ky" in sys.argv:
        dang_ky_menu()
        return
    chay()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — traceback mặc định có URL kèm token bot / Meta → che rồi mới in
        print(fb.an_bi_mat(traceback.format_exc()), flush=True)
        raise SystemExit(1) from None
