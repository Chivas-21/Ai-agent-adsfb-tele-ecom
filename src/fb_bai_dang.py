"""Tìm sản phẩm trong DB và bài đăng chạy ads tốt nhất cho 1 sản phẩm (dùng bởi fb_ads_form.py).

Bài tốt nhất = bài đã từng chạy ads (tên chiến dịch / quảng cáo chứa mã SP hoặc từ khoá),
xếp theo chi phí / tin nhắn thấp nhất (bài ra dưới 20 tin xếp sau vì ít dữ liệu).
Token hiện không đọc được bài trên page (thiếu pages_read_user_content) nên bài chưa từng chạy ads không thấy.
"""
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import cau_hinh
import fb_ads_create as fb

DB = Path(__file__).resolve().parent.parent / "data" / "commercial_engine.db"
TIN_NHAN = "onsite_conversion.messaging_conversation_started_7d"
IT_DU_LIEU = 20


def tim_san_pham(q: str, limit: int = 15) -> list[dict]:
    """Tìm sản phẩm cha / sản phẩm lẻ theo tên hoặc mã."""
    q = (q or "").strip()
    if len(q) < 2 or not DB.exists():
        return []
    with sqlite3.connect(DB) as c:
        rows = c.execute(
            "select sku, name, retail_price from products "
            "where parent_id < 0 and status = 1 and (name like ? or sku like ?) order by name limit ?",
            (f"%{q}%", f"%{q}%", limit)).fetchall()
    return [{"ma": r[0], "ten": r[1], "gia": r[2]} for r in rows]


# Khoá flexible_spec của Meta ↔ nhãn tiếng Việt hiện trên trang / trong yêu cầu gửi Claude
LOAI = {"interests": "Sở thích", "behaviors": "Hành vi", "family_statuses": "Phụ huynh",
        "life_events": "Sự kiện trong đời", "relationship_statuses": "Mối quan hệ", "industries": "Ngành nghề",
        "work_positions": "Chức danh", "education_statuses": "Học vấn", "income": "Thu nhập"}


def _loai_tu_path(path: list[str]) -> str:
    """Suy khoá flexible_spec từ đường dẫn danh mục Meta (kết quả gợi ý không kèm type)."""
    p = " › ".join(path or [])
    if p.startswith("Hành vi"):
        return "behaviors"
    if "Phụ huynh" in p or "Cha mẹ" in p:
        return "family_statuses"
    if "Sự kiện trong đời" in p:
        return "life_events"
    if "Chức danh" in p:
        return "work_positions"
    if "Mối quan hệ" in p and p.startswith("Nhân khẩu học"):
        return "relationship_statuses"
    return "interests"


def _muc(x: dict, loai: str | None = None) -> dict:
    return {"id": str(x["id"]), "name": x["name"], "loai": loai or x.get("type") or _loai_tu_path(x.get("path", [])),
            "nhom": " › ".join((x.get("path") or [])[:-1]),
            "co_mo": x.get("audience_size_upper_bound") or x.get("audience_size")}


# ---------------------------------------------------------------- bài đăng theo sản phẩm (nhúng vào trang)

CACHE_BAI = DB.parent / "bai_dang_cache.json"
TU_CHUNG = list(cau_hinh.lay("meta.tu_chung_san_pham", []) or [])
# Tài khoản QC quét bài đã chạy ads / sở thích hay dùng (quét hết mọi tài khoản lâu và dễ chạm giới hạn tần suất)
TK_QUET = [fb.TAI_KHOAN[t] for t in (cau_hinh.lay("meta.tai_khoan_quet_bai") or [fb.TAI_KHOAN_MAC_DINH])]


def _get_url(url: str, params: dict | None = None, lan: int = 4) -> dict:
    """GET 1 URL Graph (trang tiếp theo), thử lại khi Meta báo lỗi tạm."""
    import time
    import requests
    for i in range(lan):
        r = requests.get(url, params=params, timeout=120)
        d = r.json() if r.content else {}
        if r.status_code == 200 and "error" not in d:
            return d
        if i == lan - 1:
            raise RuntimeError(f"Meta lỗi {r.status_code}: {(d.get('error') or {}).get('message', r.text[:200])}")
        time.sleep(3 * (i + 1))
    return {}


def _tat_ca(path: str, params: dict) -> list[dict]:
    url, p, ra = f"{fb.GRAPH}/{path}", {**params, "access_token": fb._token()}, []
    while url:
        d = _get_url(url, p)
        ra += d.get("data", [])
        url, p = d.get("paging", {}).get("next"), None
    return ra


def _insights_ad(acc: str) -> dict[str, tuple[float, int]]:
    """Chi tiêu + tin nhắn trọn đời theo ad_id — báo cáo chạy ngầm (level=ad quá nhiều dòng cho gọi thường)."""
    import time
    job = fb._goi("POST", f"act_{acc}/insights", {"level": "ad", "date_preset": "maximum",
                                                   "fields": "ad_id,spend,actions", "limit": 500})
    rid = job["report_run_id"]
    for _ in range(120):
        st = fb._goi("GET", rid, {"fields": "async_status,async_percent_completion"})
        if st.get("async_status") == "Job Completed":
            break
        if st.get("async_status") in ("Job Failed", "Job Skipped"):
            raise RuntimeError(f"Báo cáo Meta lỗi: {st}")
        time.sleep(5)
    ra = {}
    for x in _tat_ca(f"{rid}/insights", {"limit": 500}):
        tin = sum(int(float(a["value"])) for a in x.get("actions", []) if a["action_type"] == TIN_NHAN)
        ra[x["ad_id"]] = (float(x.get("spend", 0) or 0), tin)
    return ra


def _khong_dau(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return re.sub(r"\s+", " ", re.sub(r"[̀-ͯ]", "", s)).strip().lower()


def _khoa_ten(ten: str) -> str:
    """'Quần - Cici Pants' → 'cici pants'; 'Chân váy Sumi Skirt' → 'sumi skirt' (bỏ từ chung ở đầu)."""
    t = _khong_dau(re.sub(r"^[^-]{1,15}-\s*", "", ten))
    for w in sorted((_khong_dau(x) for x in TU_CHUNG), key=len, reverse=True):
        if t.startswith(w + " "):
            t = t[len(w) + 1:]
            break
    return t


def bai_theo_san_pham(top: int = 8) -> dict:
    """{ma_sp: [bài...]} từ toàn bộ quảng cáo 2 tài khoản — khớp mã SP hoặc tên SP trong tên chiến dịch / quảng cáo."""
    bai = defaultdict(lambda: {"chi": 0.0, "tin": 0, "so_qc": 0, "ten_camp": set(), "tk": set(), "moi_nhat": "", "noi_dung": ""})
    for acc in TK_QUET:   # tài khoản chạy chính (meta.tai_khoan_quet_bai)
        tk = next(k for k, v in fb.TAI_KHOAN.items() if v == acc)
        so_lieu = _insights_ad(acc)
        for a in _tat_ca(f"act_{acc}/ads", {"fields": "id,name,created_time,campaign{name},"
                                                      "creative{body,effective_object_story_id}", "limit": 200}):
            cr = a.get("creative") or {}
            pid = cr.get("effective_object_story_id")
            if not pid:
                continue
            chi, tin = so_lieu.get(a["id"], (0.0, 0))
            b = bai[pid]
            b["chi"] += chi
            b["tin"] += tin
            b["so_qc"] += 1
            b["ten_camp"].add((a.get("campaign") or {}).get("name", ""))
            b["ten_camp"].add(a.get("name", ""))
            b["tk"].add(tk)
            b["moi_nhat"] = max(b["moi_nhat"], a.get("created_time", "")[:10])
            if not b["noi_dung"] and cr.get("body"):
                b["noi_dung"] = re.sub(r"\s+", " ", cr["body"])[:160]
    for b in bai.values():
        b["_tim"] = _khong_dau(" || ".join(b["ten_camp"]))

    with sqlite3.connect(DB) as c:
        sp = c.execute("select sku, name from products where parent_id < 0 and status = 1").fetchall()
    ra = {}
    for sku, ten in sp:
        k_ma, k_ten = _khong_dau(sku), _khoa_ten(ten)
        khop = [(pid, b) for pid, b in bai.items()
                if k_ma in b["_tim"] or (len(k_ten) >= 4 and k_ten in b["_tim"])]
        if not khop:
            continue
        ds = [{"post": pid, "chi": round(b["chi"]), "tin": b["tin"],
               "chi_moi_tin": round(b["chi"] / b["tin"]) if b["tin"] else None, "so_qc": b["so_qc"],
               "tai_khoan": sorted(b["tk"]), "moi_nhat": b["moi_nhat"], "noi_dung": b["noi_dung"],
               "link": f"https://www.facebook.com/{pid}"} for pid, b in khop]
        ds.sort(key=lambda x: (x["tin"] < IT_DU_LIEU, x["chi_moi_tin"] or 10**9))
        ra[sku] = ds[:top]
    return ra


def bai_theo_san_pham_cache(toi_da_gio: float = 12, lam_moi: bool = False) -> dict:
    """Đọc cache data/bai_dang_cache.json; quá hạn (hoặc lam_moi) thì lấy lại từ Meta (vài phút)."""
    import json
    import time
    if not lam_moi and CACHE_BAI.exists() and time.time() - CACHE_BAI.stat().st_mtime < toi_da_gio * 3600:
        return json.loads(CACHE_BAI.read_text(encoding="utf-8"))
    from datetime import datetime
    try:
        d = {"luc": datetime.now().strftime("%H:%M %d/%m/%Y"), "bai": bai_theo_san_pham()}
    except RuntimeError:
        if CACHE_BAI.exists():  # Meta giới hạn tần suất → dùng bản cũ
            return json.loads(CACHE_BAI.read_text(encoding="utf-8"))
        raise
    CACHE_BAI.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


# ---------------------------------------------------------------- quét bài viết trên page (cả bài chưa chạy ads)

CACHE_PAGE = DB.parent / "bai_page_cache.json"


def quet_bai_page(thang: int = 12, page_id: str = fb.PAGE_ID) -> list[dict]:
    """Bài đã đăng trên 1 page trong `thang` tháng gần nhất (dùng token của page).

    Cảm xúc (like, tim, icon…) + bình luận cần quyền pages_read_user_content: có quyền thì lấy, chưa có thì
    để None (trang hiện "–"). Lượt chia sẻ đọc được với quyền hiện tại.
    """
    import requests
    from datetime import datetime, timedelta
    tu = (datetime.now() - timedelta(days=30 * thang)).strftime("%Y-%m-%d")
    tok = fb.page_token(page_id)
    co_ban = "id,message,created_time,permalink_url,is_eligible_for_promotion,status_type,shares"
    tuong_tac = ",reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)"
    thu = requests.get(f"{fb.GRAPH}/{page_id}/published_posts",
                       params={"fields": co_ban + tuong_tac, "limit": 1, "access_token": tok}, timeout=60).json()
    co_tuong_tac = "error" not in thu
    url = f"{fb.GRAPH}/{page_id}/published_posts"
    # trang 100 bài bị Meta từ chối ("Please reduce the amount of data…", lỗi 500) → 25 bài/trang
    p = {"fields": co_ban + (tuong_tac if co_tuong_tac else ""), "since": tu, "limit": 25, "access_token": tok}
    ra = []
    while url:
        d = _get_url(url, p)
        for x in d.get("data", []):
            ra.append({"post": x["id"], "ngay": x.get("created_time", "")[:10],
                       "noi_dung": re.sub(r"\s+", " ", x.get("message") or "")[:400],
                       "link": x.get("permalink_url") or f"https://www.facebook.com/{x['id']}",
                       "chay_duoc": x.get("is_eligible_for_promotion"), "loai": x.get("status_type", ""),
                       "chia_se": (x.get("shares") or {}).get("count", 0),
                       "cam_xuc": (x.get("reactions") or {}).get("summary", {}).get("total_count") if co_tuong_tac else None,
                       "binh_luan": (x.get("comments") or {}).get("summary", {}).get("total_count") if co_tuong_tac else None})
        url, p = d.get("paging", {}).get("next"), None
    return ra


def _khoa_sp(sku: str, ten: str) -> list[str]:
    """Khoá khớp 1 sản phẩm trong nội dung bài: tên rút gọn, mã kiểu 'VL103'/'QL01', SKU."""
    k = {_khong_dau(sku)}
    t = _khoa_ten(ten)
    if len(t) >= 4:
        k.add(t)
    for m in re.findall(r"\b([A-Za-z]{1,3}\d{2,4})\b", ten):
        k.add(m.lower())
    return [x for x in k if x]


def bai_page_theo_san_pham(top: int = 12, thang: int = 12) -> dict:
    """{ma_sp: [bài trên các page (fb.PAGES) nói về SP, mới nhất trước]} — gồm cả bài chưa từng chạy ads.

    Mỗi page giữ tối đa `top` bài / SP; post = '<page>_<bài>' để trang lọc theo page đã chọn.
    """
    so_bai_page = {}
    bai = []
    for pid, _ in fb.PAGES.values():
        ds = quet_bai_page(thang, pid)
        so_bai_page[pid] = len(ds)
        bai += ds
    for b in bai:
        b["_tim"] = _khong_dau(b["noi_dung"])
    with sqlite3.connect(DB) as c:
        sp = c.execute("select sku, name from products where parent_id < 0 and status = 1").fetchall()
    ra = {}
    for sku, ten in sp:
        khoa = _khoa_sp(sku, ten)
        khop = [b for b in bai if any(re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", b["_tim"]) for k in khoa)]
        if khop:
            khop.sort(key=lambda b: b["ngay"], reverse=True)
            dem, giu = {}, []
            for b in khop:  # tối đa `top` bài mỗi page
                pid = b["post"].split("_")[0]
                dem[pid] = dem.get(pid, 0) + 1
                if dem[pid] <= top:
                    giu.append({k: v for k, v in b.items() if k != "_tim"} | {"noi_dung": b["noi_dung"][:160]})
            ra[sku] = giu
    return {"so_bai": len(bai), "so_bai_page": so_bai_page, "bai": ra, "bst": bai_theo_bst(bai, top)}


# "BST Everyday Moments", "bộ sưu tập “Nắng”", "#BSTPhongHoa" — tên BST trong nội dung bài (chủ trang 19/10/2026:
# ngoài tên sản phẩm, tìm bài theo bộ sưu tập). Nhanh không có trường BST nên chỉ dựa vào chữ trong bài.
_BST = re.compile(r"(?:#?\bBST|\b[Bb][ộo] s[ưu]u t[ậa]p)\s*[:\-–]?\s*(?:[\"“'‘]([^\"”’'\n]{2,40})[\"”’']|(\S+(?: \S+){0,3}))")
_BST_BO = {"moi", "nay", "cua", (cau_hinh.lay("ten_ngan") or "").lower(), _khong_dau(cau_hinh.lay("ten") or "")}


def _ten_bst(m: re.Match) -> str:
    """Tên trong ngoặc kép giữ nguyên; không ngoặc thì lấy các từ viết hoa đầu chữ liền nhau (BST Phong Hoa mới →
    'Phong Hoa'); '#BSTPhongHoa' → 'PhongHoa'."""
    if m.group(1):
        return m.group(1).strip()
    tu = []
    for w in m.group(2).split():
        w = w.strip(".,!?:;()[]#")
        if not w or not (w[0].isupper() or w[0].isdigit()):
            break
        tu.append(w)
    return " ".join(tu)


def bai_theo_bst(bai: list[dict], top: int = 12) -> dict:
    """{tên BST: [bài nhắc BST đó, mới nhất trước, tối đa `top` bài mỗi page]}."""
    import unicodedata
    nhom: dict[str, dict] = {}
    for b in bai:
        # NFKC: chữ "đậm/nghiêng" kiểu 𝐄𝐯𝐞𝐫𝐲𝐝𝐚𝐲 → Everyday
        for m in _BST.finditer(unicodedata.normalize("NFKC", b["noi_dung"])):
            ten = _ten_bst(m)
            k = _khong_dau(ten).replace(" ", "")      # "Phong Hoa" = "PhongHoa"
            if len(k) < 3 or _khong_dau(ten) in _BST_BO:
                continue
            g = nhom.setdefault(k, {"ten": {}, "bai": {}})
            g["ten"][ten] = g["ten"].get(ten, 0) + 1
            g["bai"][b["post"]] = b
    # "Phong Hoa Cảm", "Phong Hoa Nàng" (câu chạy theo tên) → gộp vào "Phong Hoa" khi tên ngắn có nhiều bài hơn
    for k in sorted(nhom, key=len, reverse=True):
        goc = next((n for n in nhom if n != k and len(n) >= 4 and k.startswith(n)
                    and len(nhom[n]["bai"]) >= max(2, len(nhom[k]["bai"]))), None)
        if goc:
            nhom[goc]["bai"].update(nhom.pop(k)["bai"])
    ra = {}
    for g in nhom.values():
        ds = sorted(g["bai"].values(), key=lambda b: b["ngay"], reverse=True)
        dem, giu = {}, []
        for b in ds:
            pid = b["post"].split("_")[0]
            dem[pid] = dem.get(pid, 0) + 1
            if dem[pid] <= top:
                giu.append({k: v for k, v in b.items() if k != "_tim"} | {"noi_dung": b["noi_dung"][:160]})
        ra[max(g["ten"], key=g["ten"].get)] = giu
    return ra


def bai_page_cache(toi_da_gio: float = 12, lam_moi: bool = False) -> dict:
    import json
    import time
    if not lam_moi and CACHE_PAGE.exists() and time.time() - CACHE_PAGE.stat().st_mtime < toi_da_gio * 3600:
        return json.loads(CACHE_PAGE.read_text(encoding="utf-8"))
    from datetime import datetime
    try:
        d = {"luc": datetime.now().strftime("%H:%M %d/%m/%Y"), **bai_page_theo_san_pham()}
    except RuntimeError as e:  # Meta lỗi tạm → dùng tạm cache cũ (nếu có)
        if not CACHE_PAGE.exists():
            raise
        print(f"Quét bài page lỗi, dùng cache cũ: {e}", file=sys.stderr)
        return json.loads(CACHE_PAGE.read_text(encoding="utf-8"))
    CACHE_PAGE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def tim_so_thich(q: str, limit: int = 10) -> list[dict]:
    """Tra sở thích (interest) trên Meta theo tên, tiếng Việt — cho target tự điền."""
    q = (q or "").strip()
    if len(q) < 2:
        return []
    r = fb._goi("GET", "search", {"type": "adinterest", "q": q, "locale": "vi_VN", "limit": limit})
    return [_muc(x, "interests") for x in r.get("data", [])]


def goi_y_lien_quan(ten: list[str], limit: int = 20) -> list[dict]:
    """Meta gợi ý sở thích / hành vi / nhân khẩu học liên quan tới các mục đã chọn (theo tên)."""
    ten = [t for t in (ten or []) if t][:10]
    if not ten:
        return []
    import json
    r = fb._goi("GET", "search", {"type": "adinterestsuggestion", "interest_list": json.dumps(ten, ensure_ascii=False),
                                  "locale": "vi_VN", "limit": limit})
    return [_muc(x) for x in r.get("data", [])]


def cay_goi_y() -> list[dict]:
    """Toàn bộ cây Duyệt của Ads Manager (sở thích, hành vi, nhân khẩu học) — nhúng vào trang lúc dựng."""
    d = fb._goi("GET", f"act_{TK_QUET[0]}/targetingbrowse", {"locale": "vi_VN"}).get("data", [])
    return [{"id": str(x["id"]), "name": x["name"], "loai": x["type"], "path": x.get("path", [])}
            for x in d if x.get("id") and x.get("type") in LOAI]


def goi_y_cache(toi_da_gio: float = 24) -> dict:
    """Cây Duyệt + mục team hay dùng, cache data/goi_y_cache.json. Meta báo giới hạn tần suất → dùng bản cũ."""
    import json
    import time
    f = DB.parent / "goi_y_cache.json"
    cu = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    if cu and time.time() - f.stat().st_mtime < toi_da_gio * 3600:
        return cu
    try:
        d = {"cay": cay_goi_y(), "hay_dung": hay_dung(), "loai": LOAI}
    except RuntimeError:
        if cu:
            return cu
        raise
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def hay_dung(top: int = 40) -> list[dict]:
    """Sở thích / hành vi / nhân khẩu học team đang dùng nhiều nhất trong các nhóm quảng cáo gần đây
    (các tài khoản trong meta.tai_khoan_quet_bai)."""
    dem, mau = defaultdict(int), {}
    for acc in TK_QUET:
        r = fb._goi("GET", f"act_{acc}/adsets", {"fields": "targeting{flexible_spec}", "limit": 200})
        for s in r.get("data", []):
            for fs in (s.get("targeting") or {}).get("flexible_spec", []):
                for loai, ds in fs.items():
                    if loai not in LOAI or not isinstance(ds, list):
                        continue
                    for x in ds:
                        if isinstance(x, dict) and x.get("id"):
                            k = (loai, str(x["id"]))
                            dem[k] += 1
                            mau[k] = x["name"]
    xep = sorted(dem.items(), key=lambda kv: -kv[1])[:top]
    return [{"id": k[1], "name": mau[k], "loai": k[0], "so_nhom": n} for k, n in xep]


def tim_tep(tai_khoan: str, q: str, limit: int = 15) -> list[dict]:
    """Tìm tệp đối tượng tuỳ chỉnh / lookalike của 1 tài khoản QC theo tên."""
    acc = fb.TAI_KHOAN.get((tai_khoan or "").strip().lower(), tai_khoan)
    q = (q or "").strip().lower()
    r = fb._goi("GET", f"act_{acc}/customaudiences", {"fields": "id,name,subtype", "limit": 300})
    ds = [{"id": a["id"], "name": a["name"], "loai": a.get("subtype")} for a in r.get("data", [])
          if not q or q in a["name"].lower()]
    return ds[:limit]


def tim_bai_dang(tu_khoa: list[str]) -> list[dict]:
    """Các bài đăng từng chạy ads khớp từ khoá, kèm chi tiêu / tin nhắn / chi phí mỗi tin, tốt nhất trước."""
    tu_khoa = [k.strip() for k in tu_khoa if k and len(k.strip()) >= 3]
    bai = defaultdict(lambda: {"chi": 0.0, "tin": 0, "so_qc": 0, "chien_dich": set(), "tai_khoan": set(),
                               "moi_nhat": "", "noi_dung": ""})
    da_xem = set()
    for tk, acc in fb.TAI_KHOAN.items():
        for truong in ("campaign.name", "ad.name"):
            for k in tu_khoa:
                r = fb._goi("GET", f"act_{acc}/ads", {
                    "fields": "id,created_time,campaign{name},creative{body,effective_object_story_id},"
                              "insights.date_preset(maximum){spend,actions}",
                    "filtering": [{"field": truong, "operator": "CONTAIN", "value": k}],
                    "limit": 200})
                for a in r.get("data", []):
                    if a["id"] in da_xem:
                        continue
                    da_xem.add(a["id"])
                    cr = a.get("creative") or {}
                    pid = cr.get("effective_object_story_id")
                    if not pid:
                        continue
                    ins = a["insights"]["data"][0] if a.get("insights") else {}
                    b = bai[pid]
                    b["chi"] += float(ins.get("spend", 0) or 0)
                    b["tin"] += sum(int(float(x["value"])) for x in ins.get("actions", [])
                                    if x["action_type"] == TIN_NHAN)
                    b["so_qc"] += 1
                    b["chien_dich"].add(a["campaign"]["name"])
                    b["tai_khoan"].add(tk)
                    b["moi_nhat"] = max(b["moi_nhat"], a["created_time"][:10])
                    if not b["noi_dung"] and cr.get("body"):
                        b["noi_dung"] = re.sub(r"\s+", " ", cr["body"])[:160]

    kq = []
    for pid, b in bai.items():
        kq.append({
            "post": pid, "chi": round(b["chi"]), "tin": b["tin"],
            "chi_moi_tin": round(b["chi"] / b["tin"]) if b["tin"] else None,
            "so_qc": b["so_qc"], "tai_khoan": sorted(b["tai_khoan"]), "moi_nhat": b["moi_nhat"],
            "chien_dich": sorted(b["chien_dich"])[:3], "noi_dung": b["noi_dung"],
            "link": f"https://www.facebook.com/{pid}",
        })
    kq.sort(key=lambda x: (x["tin"] < IT_DU_LIEU, x["chi_moi_tin"] or 10**9))
    return kq
