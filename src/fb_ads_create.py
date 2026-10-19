"""Lên chiến dịch Facebook Ads (Tin nhắn Messenger) theo khuôn chuẩn của team.

Trạng thái khi tạo: CHIẾN DỊCH TẮT, nhóm + quảng cáo BẬT. Chưa bật chiến dịch thì không tiêu tiền;
bật chiến dịch trên Ads Manager là chạy (đúng giờ bat_dau nếu có hẹn).

Khuôn chép từ các chiến dịch "... - TSH" đang chạy trên tài khoản Lamme 3 (đọc qua API 29/09/2026):
    Chiến dịch  OUTCOME_ENGAGEMENT, ngân sách ở cấp nhóm (ABO)
                tên: "<Mã SP> | <Tên SP> - <hậu tố> - <DD/MM ngày lên camp>"
    Nhóm        mỗi đối tượng chọn = 1 nhóm (đối tượng ở fb_doi_tuong.py), tên:
                "<Danh mục> | <Tên SP> - VN - Adv <bật/tắt> - <nhắm vào> - Loại trừ : <có/không>"
                mặc định BROAD 80.000đ + LAL MUA HÀNG 60.000đ
                tối ưu CONVERSATIONS → Messenger của page L'AMME, nữ, VN, chỉ mobile
    Quảng cáo   chạy cho 1 bài đăng có sẵn trên page (object_story_id), mỗi nhóm 1 quảng cáo

Chạy:
    python src/fb_ads_create.py --ds-doi-tuong                              # xem các đối tượng chọn được
    python src/fb_ads_create.py --file data/fb_ads_len_camp.csv            # xem trước, KHÔNG tạo gì
    python src/fb_ads_create.py --file data/fb_ads_len_camp.csv --tao      # tạo thật, chiến dịch TẮT
    python src/fb_ads_create.py --ma GT-CDK-S26T-0267 --danh-muc Váy --ten "Sumi Skirt" --post 1680643313630388 \
        --doi-tuong "broad+int_vay:70000+lal_muahang"
    python src/fb_ads_create.py --kiem-tra                                  # token có tạo được không

Script KHÔNG bao giờ bật chiến dịch. Duyệt trên Ads Manager rồi tự bật chiến dịch.
Cần META_ACCESS_TOKEN trong config/.env có quyền ads_management. Xem docs/fb_ads_len_camp.md.
"""
import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

import cau_hinh
from fb_doi_tuong import DOI_TUONG, KHONG_LOAI_TRU, LOAI_TRU_DA_MUA, MAC_DINH

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "config" / ".env")

# Thông tin riêng doanh nghiệp (page, tài khoản QC, hậu tố tên, danh mục, vị trí…) đọc từ config/doanh_nghiep.yaml
_META = cau_hinh.lay("meta", {}) or {}
GRAPH = f"https://graph.facebook.com/{_META.get('graph', 'v23.0')}"
# Page chạy quảng cáo (trang "Yêu cầu lên camp FB" chọn ở mục 1): mã → (ID, tên)
PAGES = {k: (str(v["id"]), v["ten"]) for k, v in (_META.get("pages") or {}).items()}
PAGE_ID = PAGES[_META.get("page_mac_dinh") or next(iter(PAGES))][0]   # page mặc định


def chon_page(s: str | None) -> str:
    """'page2' | ID page | tên page | 'Thời Trang L'amme (102731431653709)' → ID page. Trống = page L'amme."""
    s = (s or "").strip()
    if not s:
        return PAGE_ID
    m = re.search(r"\d{8,}", s)
    for k, (pid, ten) in PAGES.items():
        if (m and m.group(0) == pid) or s.lower() in (k, ten.lower()):
            return pid
    raise ValueError(f"page '{s}' không có trong danh sách — dùng: " + ", ".join(f"{k} ({t})" for k, (_, t) in PAGES.items()))


def ten_page(pid: str) -> str:
    return next((t for p, t in PAGES.values() if p == pid), pid)

# Tài khoản QC: tên ngắn → ID (không có "act_")
TAI_KHOAN = {k: str(v) for k, v in (_META.get("tai_khoan") or {}).items()}
TAI_KHOAN_MAC_DINH = _META.get("tai_khoan_mac_dinh") or next(iter(TAI_KHOAN))

# Tên chiến dịch: "<Mã SP> | <Tên SP> - <hậu tố> - <DD/MM ngày lên camp>"
HAU_TO_MAC_DINH = _META.get("hau_to_chien_dich") or "Camp"

# Mục tiêu hiệu quả (Ads Manager → Nhóm quảng cáo → Mục tiêu hiệu quả), đích Messenger.
# "gia_tri" (VALUE) Meta chưa cho đặt qua API (lỗi 2490408, kể cả sửa nhóm có sẵn — thử 30/09/2026):
# tạo bằng "mua_hang" và báo để đổi tay trên Ads Manager.
MUC_TIEU = {
    "tro_chuyen": ("CONVERSATIONS", "Tối đa hóa số cuộc trò chuyện"),
    "mua_hang": ("MESSAGING_PURCHASE_CONVERSION", "Tối đa hóa số lượt mua qua tin nhắn"),
    "gia_tri": ("VALUE", "Tối đa hóa giá trị của lượt mua qua tin nhắn"),
}
MUC_TIEU_MAC_DINH = _META.get("muc_tieu_mac_dinh") or "tro_chuyen"
MUC_TIEU_API_CHAN = {"gia_tri": "mua_hang"}

# Danh mục sản phẩm — đứng đầu tên nhóm quảng cáo: "<Danh mục> | <Tên SP> - <Target>"
DANH_MUC = list(_META.get("danh_muc") or [])

VI_TRI = _META.get("vi_tri") or {"publisher_platforms": ["facebook", "instagram"], "device_platforms": ["mobile"]}
DIA_LY = _META.get("dia_ly") or {"countries": ["VN"], "location_types": ["home", "recent"]}
GIOI_TINH = list(_META.get("gioi_tinh", [2]))   # 1 nam, 2 nữ; [] = tất cả
TINH_VIET_TAT = {"Hà Nội": "HN", "Thành phố Hồ Chí Minh": "HCM", "Đà Nẵng": "ĐN", "Hải Phòng": "HP", "Cần Thơ": "CT"}


# ---------------------------------------------------------------- gọi API

_BI_MAT = re.compile(r"(access_token|input_token|client_secret|appsecret_proof)=[^&\s'\"]+"
                     r"|EAA[A-Za-z0-9]{20,}|\b\d{8,10}:AA[A-Za-z0-9_-]{30,}\b")


def an_bi_mat(text: str) -> str:
    """Che token trong chuỗi lỗi trước khi ghi ra chỗ người khác đọc được (trang yêu cầu, nhóm Telegram, log).

    Lỗi mạng của requests (ConnectionError…) chứa nguyên URL kèm ?access_token=… — kiểm 02/10/2026.
    """
    return _BI_MAT.sub(lambda m: (m.group(1) + "=***") if m.group(1) else "***", str(text))


def _token() -> str:
    t = (os.getenv("META_ACCESS_TOKEN") or "").strip().strip("'\"")
    if not t:
        raise SystemExit("Thiếu META_ACCESS_TOKEN trong config/.env.")
    return t


def _goi(method: str, path: str, params: dict) -> dict:
    data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
            for k, v in params.items()}
    data["access_token"] = _token()
    import time
    for lan in range(5):
        try:
            if method == "GET":
                r = requests.get(f"{GRAPH}/{path}", params=data, timeout=90)
            else:
                r = requests.post(f"{GRAPH}/{path}", data=data, timeout=90)
        except requests.exceptions.RequestException as e:
            if method == "GET" and lan < 4:
                time.sleep(15)
                continue
            # POST hết giờ: Meta có thể đã tạo xong — báo lỗi (không tự gửi lại kẻo trùng), kiểm tra trên Ads Manager
            raise RuntimeError(f"Meta không trả lời ({type(e).__name__}) khi gọi {path} — có thể đã tạo, "
                               "chạy lại với --vao-camp để bổ sung phần thiếu") from None
        kq = r.json() if r.content else {}
        e = kq.get("error", {}) if isinstance(kq, dict) else {}
        # 4/17/613 = giới hạn tần suất, 2 = lỗi tạm của Meta → chờ rồi thử lại (30s, 60s, 90s, 120s)
        if e.get("code") in (2, 4, 17, 613) and lan < 4:
            time.sleep(30 * (lan + 1))
            continue
        break
    if r.status_code != 200 or "error" in kq:
        e = kq.get("error", {})
        chi_tiet = e.get("error_user_msg") or e.get("message") or r.text[:300]
        raise RuntimeError(f"Meta lỗi {r.status_code} (code {e.get('code')}/{e.get('error_subcode')}): {chi_tiet}")
    return kq


def kiem_tra_ket_noi() -> None:
    """In quyền của token và thử tạo chiến dịch ở chế độ validate_only (Meta kiểm tra, KHÔNG tạo gì)."""
    quyen = sorted(p["permission"] for p in _goi("GET", "me/permissions", {}).get("data", [])
                   if p.get("status") == "granted")
    print("Quyền của token:", ", ".join(quyen))
    for tk, acc in TAI_KHOAN.items():
        try:
            _goi("POST", f"act_{acc}/campaigns", {
                "name": "KIEM TRA QUYEN", "objective": "OUTCOME_ENGAGEMENT", "special_ad_categories": [],
                "is_adset_budget_sharing_enabled": False, "status": "PAUSED",
                "execution_options": ["validate_only"],
            })
            print(f"  OK   {tk} ({acc}) — được phép tạo chiến dịch")
        except RuntimeError as e:
            print(f"  LỖI  {tk} ({acc}) — {e}")


def kiem_tra_quyen() -> None:
    quyen = {p["permission"] for p in _goi("GET", "me/permissions", {}).get("data", [])
             if p.get("status") == "granted"}
    if "ads_management" not in quyen:
        raise SystemExit(
            "Token hiện tại thiếu quyền ads_management (đang có: " + ", ".join(sorted(quyen)) + ").\n"
            "Cấp lại token: Graph API Explorer > chọn app Meta của bạn > Add permissions > tích\n"
            "ads_read + ads_management + pages_read_engagement > Generate Access Token,\n"
            "rồi chạy: python src/get_fb_token.py  và dán token dài hạn vào META_ACCESS_TOKEN trong config/.env.\n"
            "Xem docs/fb_ads_len_camp.md."
        )


# ---------------------------------------------------------------- dựng payload

def page_token(page_id: str = PAGE_ID) -> str:
    """Token của page (lấy từ token người dùng qua me/accounts) — chỉ dùng để đọc."""
    for x in _goi("GET", "me/accounts", {"fields": "id,access_token", "limit": 100}).get("data", []):
        if x["id"] == page_id:
            return x["access_token"]
    raise RuntimeError(f"Token không quản lý page {ten_page(page_id)} — không lấy được page token.")


def _video_sang_post(video_id: str, page_id: str = PAGE_ID) -> str:
    r = requests.get(f"{GRAPH}/{video_id}", params={"fields": "post_id", "access_token": page_token(page_id)},
                     timeout=60).json()
    if not r.get("post_id"):
        raise ValueError(f"Không đổi được video/reel {video_id} sang bài đăng: {(r.get('error') or {}).get('message', r)}")
    return r["post_id"]


def _la_album(osid: str, page_id: str = PAGE_ID) -> bool:
    """Bài nhiều ảnh (album)? Meta không tạo được QC tin nhắn từ chính bài album: có nút "Gửi tin nhắn" thì lỗi mù
    1487390, bỏ nút thì lỗi 1487891 "không tương thích mục tiêu" (thử 19/10/2026) → tao() dựng QC carousel mới
    từ ảnh + nội dung của bài (_creative_album)."""
    r = requests.get(f"{GRAPH}/{osid}", params={"fields": "attachments{type}", "access_token": page_token(page_id)},
                     timeout=60).json()
    return any(a.get("type") == "album" for a in (r.get("attachments") or {}).get("data", []))


def _creative_album(acc: str, osid: str, them: dict) -> dict:
    """Payload nội dung QC carousel (tối đa 10 ảnh) dựng từ bài album: cùng chữ, cùng ảnh, nút "Gửi tin nhắn".

    Đây là bài QC mới (không cộng tương tác vào bài gốc). Meta chỉ cho tạo khi app của token ở chế độ Live —
    app đang ở chế độ phát triển thì lỗi 1885183 (19/10/2026)."""
    import base64
    page_id = osid.split("_")[0]
    p = requests.get(f"{GRAPH}/{osid}", params={
        "fields": "message,attachments{type,subattachments.limit(10){media{image}}}",
        "access_token": page_token(page_id)}, timeout=60).json()
    anh = [s["media"]["image"]["src"] for a in (p.get("attachments") or {}).get("data", [])
           for s in (a.get("subattachments") or {}).get("data", []) if (s.get("media") or {}).get("image")][:10]
    if len(anh) < 2:
        raise ValueError(f"Không đọc được ảnh của bài album {osid.split('_')[-1]} để dựng QC carousel.")
    cta = {"type": "MESSAGE_PAGE", "value": {"app_destination": "MESSENGER"}}
    link = "https://fb.com/messenger_doc/"
    the = []
    for src in anh:
        r = _goi("POST", f"{acc}/adimages", {"bytes": base64.b64encode(requests.get(src, timeout=60).content).decode()})
        the.append({"image_hash": next(iter(r["images"].values()))["hash"], "link": link, "name": " ", "call_to_action": cta})
    return {"object_story_spec": {"page_id": page_id, "link_data": {
        "message": p.get("message") or "", "link": link, "call_to_action": cta, "child_attachments": the,
        "multi_share_end_card": False, "multi_share_optimized": False}}, **them}


def _post_id(s: str, page_id: str = PAGE_ID) -> str:
    """Nhận '1680643313630388', '<page>_<post>' hoặc link .../posts/<số>. Trả về '<page>_<post>'.

    Bài phải thuộc page chạy quảng cáo (promoted_object) — '<page khác>_<post>' bị từ chối.
    """
    s = (s or "").strip()
    if re.fullmatch(r"\d+_\d+", s):
        if s.split("_")[0] != page_id:
            raise ValueError(f"Bài {s} thuộc page {ten_page(s.split('_')[0])}, không phải page {ten_page(page_id)} đã chọn.")
        return s
    if re.fullmatch(r"\d+", s):
        # Số trần có thể là ID reel/video (trang "Quét bài trên page" đưa ID reel): '<page>_<ID video>' Meta vẫn đọc
        # được nhưng tạo nội dung QC lỗi 1487390 → đổi sang ID bài đăng (10/10/2026, 3 yêu cầu Uni Pants)
        r = requests.get(f"{GRAPH}/{s}", params={"fields": "post_id,from", "access_token": page_token(page_id)},
                         timeout=60).json()
        if r.get("post_id"):
            chu = (r.get("from") or {}).get("id")
            if chu and chu != page_id:   # video của page khác → Meta báo lỗi mù 2446187
                raise ValueError(f"Bài {s} là video của page {ten_page(chu)}, không phải page {ten_page(page_id)} đã chọn"
                                 " — chọn lại đúng page hoặc bài khác.")
            return f"{page_id}_{r['post_id']}"
        # ID 1 ảnh (photo.php?fbid=…&set=a.<album>) — kể cả ảnh "tách" từ bài nhiều ảnh: '<page>_<ID ảnh>' Meta đọc được
        # nhưng tạo nội dung QC lỗi mù 1487390 → đổi sang bài chứa ảnh; bài đó là album thì _kiem_album báo rõ (14/10/2026)
        r = requests.get(f"{GRAPH}/{s}", params={"fields": "page_story_id", "access_token": page_token(page_id)},
                         timeout=60).json()
        if (r.get("page_story_id") or "").startswith(f"{page_id}_") and r["page_story_id"] != f"{page_id}_{s}":
            return r["page_story_id"]
        # Không phải video: bài phải nằm trên page đã chọn; bài của page Lamme khác thì báo rõ
        if "error" in requests.get(f"{GRAPH}/{page_id}_{s}", params={"fields": "id", "access_token": page_token(page_id)},
                                   timeout=60).json():
            for pid, _ in PAGES.values():
                if pid != page_id and "error" not in requests.get(
                        f"{GRAPH}/{pid}_{s}", params={"fields": "id", "access_token": page_token(pid)}, timeout=60).json():
                    raise ValueError(f"Bài {s} thuộc page {ten_page(pid)}, không phải page {ten_page(page_id)} đã chọn"
                                     " — chọn lại đúng page hoặc bài khác.")
        return f"{page_id}_{s}"
    m = re.search(r"(?:/reel/|/reels/|/videos/|[?&]v=)(\d{8,})", s)
    if m:  # link reel/video: số trong link là ID video, phải đổi sang ID bài đăng (lỗi 1487472 nếu dùng thẳng)
        return f"{page_id}_{_video_sang_post(m.group(1), page_id)}"
    m = re.search(r"(?:posts|story_fbid=|fbid=)/?(\d{8,})", s)
    if m:
        return f"{page_id}_{m.group(1)}"
    raise ValueError(
        f"Không đọc được ID bài đăng từ '{s}'. Dùng ID số của bài (link dạng pfbid... không tách được —\n"
        "  mở bài trên Meta Business Suite, ID số nằm trong link)."
    )


def _khong_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return re.sub(r"[̀-ͯ\s]", "", s).lower()


def chon_danh_muc(s: str | None) -> str:
    """Khớp danh mục không phân biệt hoa thường / dấu / khoảng trắng: 'ao dai' → 'Áo dài'."""
    can = _khong_dau(s or "")
    for dm in DANH_MUC:
        if _khong_dau(dm) == can:
            return dm
    raise ValueError(f"danh mục '{s or ''}' không hợp lệ — chọn 1 trong: {', '.join(DANH_MUC)}")


def _mau_tro_chuyen(ma: str | None) -> dict:
    """Mã mẫu cuộc trò chuyện (fb_mau_tro_chuyen) → {"page_welcome_message": ...}; trống / "khong" → {}."""
    ma = (ma or "").strip().lower()
    if not ma or ma in ("khong", "không", "0"):
        return {}
    import fb_mau_tro_chuyen  # nhập muộn: module này import ngược fb_ads_create
    return {"page_welcome_message": fb_mau_tro_chuyen.json_mau(ma)}


def them_target_tu_dien(ma: str, ten_nhom: str, tuoi: tuple[int, int], adv: bool,
                        so_thich: list[dict] | None = None, tep: dict | None = None,
                        ngan_sach: int = 60_000, dia_ly: list[dict] | None = None) -> str:
    """Đăng ký tạm 1 target người dùng tự điền (trang "Yêu cầu lên camp FB") vào DOI_TUONG, trả về mã.

    so_thich: [{"id","name","loai"}] — loai là khoá flexible_spec (interests, behaviors, family_statuses, life_events,
    work_positions…; mặc định interests), các mục là HOẶC; tep: {account_id: [{"id","name"}]};
    dia_ly: tỉnh/thành [{"key","name"}] (mã region của Meta, xem tinh_vn()) — trống = cả Việt Nam.
    Advantage+ bật thì Meta bắt tuổi tối đa 65 và tối thiểu ≤ 25 — độ tuổi điền vào thành gợi ý.
    """
    lo, hi = int(tuoi[0]), int(tuoi[1])
    dt = {"ten_nhom": ten_nhom, "mo_ta": "Target tự điền", "adv": 1 if adv else 0, "ngan_sach": int(ngan_sach),
          "tuoi": (min(lo, 25), 65) if adv else (lo, hi)}
    if adv:
        dt["goi_y"] = (lo, hi)
    if so_thich:
        nhom: dict[str, list] = {}
        for x in so_thich:
            nhom.setdefault(x.get("loai") or "interests", []).append({"id": str(x["id"]), "name": x["name"]})
        dt["so_thich"] = [nhom]
    if tep:
        dt["tep"] = tep
    if dia_ly:
        dt["dia_ly"] = [{"key": str(x["key"]), "name": x["name"]} for x in dia_ly]
    DOI_TUONG[ma] = dt
    return ma


def chon_doi_tuong(s: str | None) -> list[tuple[str, int | None]]:
    """'broad+int_vay:70000, lal_muahang' → [('broad', None), ('int_vay', 70000), ('lal_muahang', None)]."""
    if not (s or "").strip():
        return [(m, None) for m in MAC_DINH]
    chon = []
    for phan in re.split(r"[+,;\s]+", s.strip()):
        if not phan:
            continue
        ma, _, ns = phan.partition(":")
        ma = ma.strip().lower()
        if ma not in DOI_TUONG:
            raise ValueError(f"đối tượng '{ma}' không có. Xem: python src/fb_ads_create.py --ds-doi-tuong")
        chon.append((ma, int(ns.replace(".", "")) if ns.strip() else None))
    return chon


def dung_targeting(ma: str, acc: str, loai_tru: bool) -> dict:
    dt = DOI_TUONG[ma]
    t = {
        "age_min": dt["tuoi"][0], "age_max": dt["tuoi"][1], "genders": list(dt.get("gioi_tinh", GIOI_TINH)),
        "geo_locations": ({"regions": [{"key": x["key"]} for x in dt["dia_ly"]], "location_types": DIA_LY["location_types"]}
                          if dt.get("dia_ly") else dt.get("geo_goc") or DIA_LY),
        "targeting_automation": {"advantage_audience": dt["adv"]}, **VI_TRI,
    }
    if "gioi" in dt:                     # đối tượng đã lưu trên Meta: giữ đúng giới tính đã lưu (None = cả nam nữ)
        t["genders"] = dt["gioi"] or []
    if not t["genders"]:
        del t["genders"]
    if dt["adv"] and dt.get("goi_y"):
        t["age_range"] = list(dt["goi_y"])
    if dt.get("so_thich"):
        t["flexible_spec"] = dt["so_thich"]
    if dt.get("tep", {}).get(acc):
        t["custom_audiences"] = dt["tep"][acc]
    elif "tep" in dt:
        dt["tep"][acc]                   # KeyError nếu tệp không thuộc tài khoản này (giống trước)
    ex = list(dt.get("loai_tru_tep", {}).get(acc, []))
    if loai_tru and ma not in KHONG_LOAI_TRU and acc in LOAI_TRU_DA_MUA:
        ex += [x for x in LOAI_TRU_DA_MUA[acc] if x["id"] not in {e["id"] for e in ex}]
    if ex:
        t["excluded_custom_audiences"] = ex
    if dt.get("loai_tru_khac"):
        t["exclusions"] = dt["loai_tru_khac"]
    return t


def viet_tat(ten: str) -> str:
    """Chữ cái đầu mỗi từ, bỏ dấu, viết hoa: 'Váy liền thân' → 'VLT', 'Làm vợ - Làm mẹ' → 'LVLM'."""
    ten = ten.split(" (")[0].replace("đ", "d").replace("Đ", "D")
    ten = unicodedata.normalize("NFD", ten)
    return "".join(w[0] for w in re.findall(r"[^\W\d_]+", re.sub(r"[̀-ͯ]", "", ten))).upper()


def doc_bat_dau(s: str | None) -> datetime | None:
    """'2026-09-30 00:00' | '30/09/2026 00:00' | '30/09 0:00' → datetime giờ VN. Trống = chạy ngay khi bật."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%d/%m %H:%M", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if "%Y" not in fmt:
            d = d.replace(year=datetime.now().year)
        if d <= datetime.now():
            raise ValueError(f"giờ bắt đầu {d:%d/%m/%Y %H:%M} đã qua")
        return d
    raise ValueError(f"không đọc được giờ bắt đầu '{s}' — dùng dạng 30/09/2026 00:00")


def ten_target(t: dict, dt: dict) -> str:
    """Phần Target của tên nhóm: 'VN - Adv tắt - VLT, TKTT, TTCC - Loại trừ : có'.

    Nhắm theo tỉnh thì 'VN' thay bằng tỉnh: 'HN, HCM' (TP lớn viết tắt); quá 3 tỉnh: 'HN, HCM +4 tỉnh'.

    Sở thích ghi viết tắt (chữ cái đầu); tệp đối tượng ghi theo tên nhóm (LAL MUA HÀNG, TỆP XEM LIVE...);
    không sở thích / tệp thì ghi 'Rộng'.
    """
    if t.get("flexible_spec"):
        nham = ", ".join(viet_tat(_ten_muc(k, i)) for fs in t["flexible_spec"] for k, v in fs.items() for i in v)
    elif t.get("custom_audiences"):
        nham = dt["ten_nhom"]
    elif dt.get("nguon") == "meta":
        nham = dt["ten_nhom"]   # tệp đã lưu rộng ("Lamme 5") — ghi "Rộng" thì trùng tên nhóm BROAD (13/10/2026)
    else:
        nham = "Rộng"
    adv = "bật" if t["targeting_automation"]["advantage_audience"] else "tắt"
    loai_tru = "có" if t.get("excluded_custom_audiences") else "không"
    vung = [TINH_VIET_TAT.get(x["name"], x["name"]) for x in dt.get("dia_ly", [])] or         [x.get("name", x["key"]) for x in (dt.get("geo_goc") or {}).get("cities", [])]
    noi = (", ".join(vung) if len(vung) <= 3 else f"{', '.join(vung[:2])} +{len(vung) - 2} tỉnh") if vung else "VN"
    return f"{noi} - Adv {adv} - {nham} - Loại trừ : {loai_tru}"


def tinh_vn(lam_moi: bool = False) -> list[dict]:
    """63 tỉnh/thành Việt Nam theo mã region của Meta [{"key","name"}] — cache data/tinh_vn.json."""
    f = ROOT / "data" / "tinh_vn.json"
    if f.exists() and not lam_moi:
        return json.loads(f.read_text(encoding="utf-8"))
    d = _goi("GET", "search", {"type": "adgeolocation", "location_types": json.dumps(["region"]),
                               "country_code": "VN", "q": "", "limit": 200})["data"]
    ds = [{"key": x["key"], "name": x["name"]} for x in d if x.get("country_code") == "VN"]
    f.write_text(json.dumps(ds, ensure_ascii=False), encoding="utf-8")
    return ds


def dung_ke_hoach(dong: dict) -> dict:
    ma = dong["ma"].strip()
    ten = re.sub(r"\s+", " ", dong["ten"]).strip()
    tk_key = (dong.get("tai_khoan") or TAI_KHOAN_MAC_DINH).strip().lower().replace(" ", "")
    acc = TAI_KHOAN.get(tk_key, tk_key)
    if acc not in TAI_KHOAN.values():
        raise ValueError(f"Tài khoản QC '{dong.get('tai_khoan')}' không hợp lệ — dùng: " + ", ".join(TAI_KHOAN))
    bat_dau = doc_bat_dau(dong.get("bat_dau"))
    ngay = (dong.get("ngay") or datetime.now().strftime("%d/%m")).strip()  # ngày lên camp, không phải ngày chạy
    hau_to = (dong.get("hau_to") or HAU_TO_MAC_DINH).strip()
    loai_tru = str(dong.get("loai_tru") or "").strip().lower() in ("1", "x", "co", "có", "yes", "true")
    page_id = chon_page(dong.get("page"))
    osid = _post_id(dong["post"], page_id)
    album = _la_album(osid, page_id)

    ten_camp = f"{ma} | {ten} - {hau_to} - {ngay}"
    ten_hoa = ten.upper()
    danh_muc = chon_danh_muc(dong.get("danh_muc"))
    muc_tieu = (dong.get("muc_tieu") or MUC_TIEU_MAC_DINH).strip().lower()
    if muc_tieu not in MUC_TIEU:
        raise ValueError(f"mục tiêu hiệu quả '{muc_tieu}' không hợp lệ — dùng: {', '.join(MUC_TIEU)}")
    canh_bao = []
    muc_tieu_api = muc_tieu
    if muc_tieu in MUC_TIEU_API_CHAN:
        muc_tieu_api = MUC_TIEU_API_CHAN[muc_tieu]
        canh_bao.append(f"Meta chưa cho đặt \"{MUC_TIEU[muc_tieu][1]}\" qua API — đã tạo với "
                        f"\"{MUC_TIEU[muc_tieu_api][1]}\"; đổi tay trong nhóm quảng cáo trên Ads Manager.")
    chung = {
        "billing_event": "IMPRESSIONS",
        "optimization_goal": MUC_TIEU[muc_tieu_api][0],
        "destination_type": "MESSENGER",
        "promoted_object": {"page_id": page_id},
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        # Không gửi attribution_spec: với CONVERSATIONS → Messenger, API chỉ nhận (1 click, 0 xem)
        # và báo lỗi 1885501 nếu gửi 7/1 như giao diện hiển thị. Để Meta tự đặt mặc định.
        # Nhóm + quảng cáo BẬT sẵn, chỉ chiến dịch TẮT — bật chiến dịch là chạy, chưa bật thì không tiêu tiền.
        "status": "ACTIVE",
    }
    if bat_dau:
        chung["start_time"] = bat_dau.strftime("%Y-%m-%dT%H:%M:%S+0700")
    nhom = []
    for ma_dt, ns in chon_doi_tuong(dong.get("doi_tuong")):
        dt = DOI_TUONG[ma_dt]
        if "tep" in dt and acc not in dt["tep"]:
            canh_bao.append(f"'{ma_dt}' chưa có tệp đối tượng ở tài khoản này — bỏ nhóm {dt['ten_nhom']}")
            continue
        t = dung_targeting(ma_dt, acc, loai_tru)
        if loai_tru and ma_dt not in KHONG_LOAI_TRU and acc not in LOAI_TRU_DA_MUA:
            canh_bao.append("tài khoản này chưa có tệp \"đã mua 90 ngày\" — bỏ qua loại trừ")
        nhom.append({
            **chung,
            "name": f"{danh_muc} | {ten} - {ten_target(t, dt)}",
            "daily_budget": ns or dt["ngan_sach"],
            "targeting": t,
        })
    if not nhom:
        raise ValueError("không còn nhóm quảng cáo nào sau khi lọc đối tượng")
    if len({n["name"] for n in nhom}) < len(nhom):
        raise ValueError("chọn trùng đối tượng")

    return {
        "account": acc,
        "page": page_id,
        "campaign": {
            "name": ten_camp,
            "objective": "OUTCOME_ENGAGEMENT",
            "special_ad_categories": [],
            "is_adset_budget_sharing_enabled": False,
            "status": "PAUSED",
        },
        "adsets": nhom,
        "ad": {
            "name": ten_hoa,
            # Không gửi degrees_of_freedom_spec.standard_enhancements: Meta đã khai tử (lỗi 3858504).
            # Nút "Gửi tin nhắn" khai báo rõ — bài reel không tự có, thiếu là lỗi 1487891 (không hợp mục tiêu)
            # Bài album: "_album" → tao() dựng QC carousel từ ảnh + chữ của bài (xem _la_album)
            "creative": {"object_story_id": osid,
                         "call_to_action": {"type": "MESSAGE_PAGE", "value": {"app_destination": "MESSENGER"}},
                         **_mau_tro_chuyen(dong.get("mau_tro_chuyen")), **({"_album": True} if album else {})},
            "status": "ACTIVE",
        },
        "canh_bao": canh_bao,
        "muc_tieu": MUC_TIEU[muc_tieu_api][1],
    }


# ---------------------------------------------------------------- tạo thật

def tao(kh: dict, camp_co_san: str | None = None) -> dict:
    """Tạo chiến dịch → nhóm → quảng cáo. Lỗi giữa chừng thì báo ID đã tạo để dọn tay.

    camp_co_san: ID chiến dịch đã tạo dở — tạo tiếp vào đó; nhóm trùng tên và nhóm đã có
    quảng cáo thì dùng lại, không tạo trùng.
    """
    acc = f"act_{kh['account']}"
    da_tao = {"campaign": camp_co_san, "adsets": [], "ads": []}
    nhom_cu = {}
    # Tạo creative TRƯỚC: bài đăng không chạy được (lỗi 1487472…) thì dừng luôn, không để lại chiến dịch tạo dở
    c = kh["ad"]["creative"]
    if c.get("_album"):
        them = {k: v for k, v in c.items() if k not in ("object_story_id", "call_to_action", "_album")}
        try:
            cr = _goi("POST", f"{acc}/adcreatives", {"name": f"{kh['ad']['name']} · carousel {c['object_story_id']}",
                                                     **_creative_album(acc, c["object_story_id"], them)})
        except RuntimeError as e:
            if "1885183" in str(e):
                raise RuntimeError(
                    "Bài album phải dựng thành QC carousel, nhưng app Meta của token còn ở chế độ phát triển nên Meta "
                    "chặn (1885183). Chủ trang bật Live cho app trên developers.facebook.com rồi gửi lại, hoặc chọn bài "
                    "video / reel / 1 ảnh.") from None
            raise
    else:
        cr = _goi("POST", f"{acc}/adcreatives", {"name": f"{kh['ad']['name']} · {c['object_story_id']}", **c})
    ad_mau = {**kh["ad"], "creative": {"creative_id": cr["id"]}}
    try:
        if camp_co_san:
            ds = _goi("GET", f"{camp_co_san}/adsets", {"fields": "id,name,ads.limit(1){id}", "limit": 50})
            nhom_cu = {s["name"]: s for s in ds.get("data", [])}
        else:
            da_tao["campaign"] = _goi("POST", f"{acc}/campaigns", kh["campaign"])["id"]
        for ns in kh["adsets"]:
            cu = nhom_cu.get(ns["name"])
            s_id = cu["id"] if cu else _goi("POST", f"{acc}/adsets", {**ns, "campaign_id": da_tao["campaign"]})["id"]
            da_tao["adsets"].append(s_id)
            if cu and cu.get("ads", {}).get("data"):
                da_tao["ads"].append(cu["ads"]["data"][0]["id"])
                continue
            ad = _goi("POST", f"{acc}/ads", {**ad_mau, "adset_id": s_id})
            da_tao["ads"].append(ad["id"])
    except RuntimeError as e:
        raise RuntimeError(f"{e}\n  Đã tạo dở (chiến dịch TẮT, không tiêu tiền): {da_tao}") from None
    return da_tao


# ---------------------------------------------------------------- chạy

COT = ["ma", "danh_muc", "ten", "post", "tai_khoan", "muc_tieu", "doi_tuong", "loai_tru", "bat_dau",
       "mau_tro_chuyen", "ngay", "hau_to"]


def doc_file(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        dong = [d for d in csv.DictReader(f) if (d.get("ma") or "").strip()]
    thieu = [c for c in ("ma", "danh_muc", "ten", "post") if dong and c not in dong[0]]
    if thieu:
        raise SystemExit(f"File thiếu cột: {', '.join(thieu)}. Cột hợp lệ: {', '.join(COT)}")
    return dong


NHAN_FLEX = {"interests": "Sở thích", "work_positions": "Chức danh", "family_statuses": "Tình trạng gia đình",
             "behaviors": "Hành vi", "life_events": "Sự kiện trong đời", "relationship_statuses": "Mối quan hệ",
             "industries": "Ngành nghề", "education_statuses": "Học vấn", "income": "Thu nhập"}


QUAN_HE = {1: "Độc thân", 2: "Đang hẹn hò", 3: "Đã kết hôn", 4: "Đã đính hôn", 6: "Chưa xác định"}


def _ten_muc(loai: str, i) -> str:
    """Tên 1 mục nhắm (sở thích, hành vi…); tình trạng mối quan hệ Meta trả số (3 = đã kết hôn)."""
    if isinstance(i, dict):
        return i.get("name") or str(i.get("id"))
    return QUAN_HE.get(i, str(i)) if loai == "relationship_statuses" else str(i)


def chi_tiet_nham_vao(t: dict) -> list[str]:
    """Nhắm vào ai — mỗi ý 1 dòng."""
    tuoi = f"{t['age_min']}-{t['age_max']}"
    if t.get("age_range"):
        tuoi += f" (gợi ý {t['age_range'][0]}-{t['age_range'][1]})"
    g = t["geo_locations"]
    vung = g.get("regions")
    if vung:
        ten = {x["key"]: x["name"] for x in tinh_vn()}
        noi = f"{len(vung)} tỉnh/thành: " + ", ".join(x.get("name") or ten.get(x["key"], x["key"]) for x in vung)
    elif g.get("cities"):
        noi = "TP " + ", ".join(x.get("name", x["key"]) + (f" +{x['radius']}{'mi' if x.get('distance_unit') == 'mile' else 'km'}"
                                                           if x.get("radius") else "") for x in g["cities"])
    else:
        noi = "Việt Nam"
    gioi = {(2,): "Nữ", (1,): "Nam"}.get(tuple(t.get("genders") or ()), "Nam + nữ")
    dong = [f"{gioi} · {tuoi} tuổi · {noi} · điện thoại",
            "Advantage+ Audience: " + ("BẬT — Meta được mở rộng ra ngoài phần nhắm dưới đây"
                                        if t["targeting_automation"]["advantage_audience"] else "tắt")]
    for fs in t.get("flexible_spec", []):
        for k, v in fs.items():
            dong.append(f"{NHAN_FLEX.get(k, k)}: "
                        + ", ".join(f"{_ten_muc(k, i).split(' (')[0]} ({viet_tat(_ten_muc(k, i))})" for i in v))
    if t.get("custom_audiences"):
        dong.append("Tệp: " + "; ".join(a["name"] for a in t["custom_audiences"]))
    if not t.get("flexible_spec") and not t.get("custom_audiences"):
        dong.append("Không giới hạn sở thích / tệp (rộng)")
    if t.get("excluded_custom_audiences"):
        dong.append("Loại trừ: " + "; ".join(a["name"] for a in t["excluded_custom_audiences"]))
    for k, v in (t.get("exclusions") or {}).items():
        dong.append(f"Loại trừ {NHAN_FLEX.get(k, k).lower()}: " + ", ".join(_ten_muc(k, i) for i in v))
    return dong


def in_ke_hoach(i: int, kh: dict) -> None:
    ten_tk = next(k for k, v in TAI_KHOAN.items() if v == kh["account"])
    print(f"\n[{i}] {kh['campaign']['name']}")
    print(f"    page {ten_page(kh.get('page', PAGE_ID))} · tài khoản {ten_tk} ({kh['account']}) · "
          f"bài đăng {kh['ad']['creative']['object_story_id']}"
          + (" (bài nhiều ảnh → QC carousel dựng từ ảnh + chữ của bài)" if kh["ad"]["creative"].get("_album") else ""))
    bd = kh["adsets"][0].get("start_time") if kh["adsets"] else None
    print(f"    bắt đầu: {datetime.strptime(bd[:16], '%Y-%m-%dT%H:%M'):%H:%M %d/%m/%Y}" if bd
          else "    bắt đầu: ngay khi bật")
    print(f"    mục tiêu hiệu quả: {kh.get('muc_tieu', '')}")
    pwm = kh["ad"]["creative"].get("page_welcome_message")
    if pwm:
        loi_chao = ((json.loads(pwm).get("text_format") or {}).get("message") or {}).get("text", "")
        print(f"    cuộc trò chuyện: {re.sub(r'\s+', ' ', loi_chao)[:70]}…")
    for ns in kh["adsets"]:
        print(f"    - {ns['name']}")
        for d in chi_tiet_nham_vao(ns["targeting"]):
            print(f"        {d}")
    for c in kh["canh_bao"]:
        print(f"    ! {c}")


def in_ds_doi_tuong() -> None:
    print("Các đối tượng chọn được (cột doi_tuong / --doi-tuong, nối bằng dấu +):")
    for ma, dt in DOI_TUONG.items():
        ban = {tk: dung_targeting(ma, acc, False) for tk, acc in TAI_KHOAN.items()
               if "tep" not in dt or acc in dt["tep"]}
        dau = next(iter(ban.values()))
        print(f"\n  {ma}  →  tên nhóm \"... - {ten_target(dau, dt)}\"")
        for d in chi_tiet_nham_vao(dau):
            if d.startswith("Tệp: ") and len({json.dumps(t.get("custom_audiences")) for t in ban.values()}) > 1:
                for tk, t in ban.items():
                    print(f"      Tệp ({tk}): " + "; ".join(a["name"] for a in t["custom_audiences"]))
            else:
                print(f"      {d}")
    print(f"\nMặc định (để trống): {' + '.join(MAC_DINH)}")
    print("Cột loai_tru = 1: loại người đã mua 90 ngày khỏi các nhóm không phải bám đuổi.")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Lên chiến dịch tin nhắn FB theo khuôn chuẩn (chiến dịch TẮT).")
    ap.add_argument("--file", help="CSV các chiến dịch cần lên (xem data/fb_ads_len_camp.csv)")
    ap.add_argument("--ma", help="Mã sản phẩm (lên 1 chiến dịch)")
    ap.add_argument("--ten", help="Tên sản phẩm")
    ap.add_argument("--post", help="ID hoặc link bài đăng trên page")
    ap.add_argument("--page", help="Page chạy quảng cáo: " + ", ".join(f"{k} = {t}" for k, (_, t) in PAGES.items())
                    + " (mặc định page1)")
    ap.add_argument("--danh-muc", help=f"Danh mục sản phẩm: {', '.join(DANH_MUC)}")
    ap.add_argument("--tai-khoan", default=TAI_KHOAN_MAC_DINH, help="tên tài khoản trong config/doanh_nghiep.yaml (meta.tai_khoan)")
    ap.add_argument("--doi-tuong", help=f"Đối tượng, nối bằng + (mặc định {'+'.join(MAC_DINH)})")
    ap.add_argument("--muc-tieu", default=MUC_TIEU_MAC_DINH, choices=list(MUC_TIEU),
                    help="Mục tiêu hiệu quả: tro_chuyen (mặc định) | mua_hang | gia_tri")
    ap.add_argument("--loai-tru", action="store_true", help="Loại người đã mua 90 ngày")
    ap.add_argument("--mau-tro-chuyen", help="Mã mẫu cuộc trò chuyện (xem: python src/fb_mau_tro_chuyen.py)")
    ap.add_argument("--bat-dau", help="Giờ bắt đầu chạy, ví dụ '30/09/2026 00:00' (trống = ngay khi bật)")
    ap.add_argument("--ds-doi-tuong", action="store_true", help="Xem danh sách đối tượng chọn được")
    ap.add_argument("--tao", action="store_true", help="Tạo thật trên Meta (mặc định chỉ xem trước)")
    ap.add_argument("--kiem-tra", action="store_true", help="Chỉ kiểm tra token có tạo được chiến dịch không")
    ap.add_argument("--vao-camp", help="ID chiến dịch tạo dở — chỉ tạo tiếp nhóm + quảng cáo vào đó (1 chiến dịch)")
    args = ap.parse_args()

    if args.ds_doi_tuong:
        in_ds_doi_tuong()
        return
    if args.kiem_tra:
        kiem_tra_ket_noi()
        return
    if args.file:
        dong = doc_file(Path(args.file))
    elif args.ma and args.ten and args.post:
        dong = [{"ma": args.ma, "danh_muc": args.danh_muc, "ten": args.ten, "post": args.post,
                 "tai_khoan": args.tai_khoan, "page": args.page,
                 "doi_tuong": args.doi_tuong, "loai_tru": "1" if args.loai_tru else "", "muc_tieu": args.muc_tieu, "mau_tro_chuyen": args.mau_tro_chuyen,
                 "bat_dau": args.bat_dau}]
    else:
        ap.error("cần --file, hoặc đủ --ma --ten --post")

    ke_hoach, loi = [], []
    for i, d in enumerate(dong, 1):
        try:
            ke_hoach.append(dung_ke_hoach(d))
        except (ValueError, KeyError) as e:
            loi.append(f"dòng {i} ({d.get('ma')}): {e}")
    for i, kh in enumerate(ke_hoach, 1):
        in_ke_hoach(i, kh)
    print(f"\nTổng: {len(ke_hoach)} chiến dịch · {sum(len(kh['adsets']) for kh in ke_hoach)} nhóm quảng cáo.")
    if loi:
        print("\nBỎ QUA:\n  " + "\n  ".join(loi))

    if not args.tao:
        print("\n(Chỉ xem trước — chưa tạo gì. Thêm --tao để tạo: chiến dịch TẮT, nhóm + quảng cáo BẬT.)")
        return

    if args.vao_camp and len(ke_hoach) != 1:
        raise SystemExit("--vao-camp chỉ dùng khi lên đúng 1 chiến dịch.")
    kiem_tra_quyen()
    print("\nĐang tạo...")
    ok = 0
    for kh in ke_hoach:
        try:
            kq = tao(kh, args.vao_camp)
            ok += 1
            print(f"  OK  {kh['campaign']['name']} → chiến dịch {kq['campaign']}, "
                  f"{len(kq['adsets'])} nhóm, {len(kq['ads'])} quảng cáo")
        except RuntimeError as e:
            print(f"  LỖI {kh['campaign']['name']}: {e}")
    print(f"\nXong {ok}/{len(ke_hoach)}. Chiến dịch đang TẮT (nhóm + quảng cáo đã bật) — "
          "duyệt trên Ads Manager rồi bật chiến dịch.")


if __name__ == "__main__":
    main()
