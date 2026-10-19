"""Hội thoại bắt đầu từ quảng cáo FB, chia theo nhân viên trả lời trên Pancake (theo ngày / tháng).

Chủ trang (05/10/2026): "tổng 1 ngày 500 tin nhắn từ lượt bắt đầu cuộc trò chuyện qua tin nhắn — mỗi tài khoản
facebook trả lời bao nhiêu tin trong 500 tin đó"; sau đó thêm tháng này / tháng trước. Nhân viên trả lời khách trên
Pancake, nên lấy từ Pancake public API (https://pages.fm/api/public_api/v1, token trang ở Cài đặt → Công cụ, không hết
hạn) — Graph API của Facebook không cho biết admin nào trả lời.

Cách đếm (khớp định nghĩa messaging_conversation_started_7d của FB — 04/10: Pancake 765, FB 838):
- Hội thoại từ QC = có lượt bấm quảng cáo (trường `ads` của hội thoại / `ad_clicks`, `activities` ADS của tin nhắn)
  VÀ khách không nhắn gì trong 7 ngày trước lần bấm đó (FB chỉ tính lại sau 7 ngày im lặng). Tính theo ngày bấm.
- Gán cho nhân viên gửi tin ĐẦU TIÊN sau lần bấm (tin có from.uid + admin_name; Botcake không có uid). Không tính
  "tham gia", vì có người nhắn chăm sóc lại hàng loạt hôm sau làm 1 hội thoại bị đếm nhiều lần.
- Tên là tên tài khoản FB trong Pancake ("Linhh Linh", "Lan Nguyễn Phạm"…), chưa ghép với tên nhân viên trên Nhanh.

Danh sách hội thoại lọc theo updated_at (order_by=updated_at) từ đầu khoảng tới bây giờ để bắt cả khách cũ quay lại
qua QC — page L'amme ~2.700 hội thoại cập nhật/ngày; tin nhắn 30 tin/lần, lùi trang bằng current_count.
Mỗi ngày tính xong được lưu vĩnh viễn ở data/pancake_tin_nhan_ngay.json (ngày đã qua ≥3 giờ thì coi là chốt), nên
/tinnhan thang|thangtruoc chỉ cộng các ngày đã lưu. Lịch Windows `\\LAMME\\TinNhanPancake` (07:40 hằng ngày) tính
trước hôm qua + bù ngày còn thiếu từ đầu tháng trước.

Cần trong config/.env: PANCAKE_TOKEN_LAMME, PANCAKE_TOKEN_DOLOTBAU, PANCAKE_TOKEN_THOITRANGLAMME (page nào thiếu token
thì bỏ qua).

    python src/pancake_tin_nhan.py                                # hôm qua
    python src/pancake_tin_nhan.py --tu 2026-09-01 --den 2026-09-30
    python src/pancake_tin_nhan.py --bu                           # lịch hằng ngày: tính + lưu ngày còn thiếu
"""
import argparse
import html
import json
import math
import os
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date, datetime, timedelta, timezone

import requests

import cau_hinh
import fb_ads_create as fb

API = "https://pages.fm/api/public_api/v1"
VN = timezone(timedelta(hours=7))
NGAY = 86400
TUAN = 7 * NGAY
LUONG = 6                       # số luồng gọi Pancake cùng lúc — gọi dồn quá thì Pancake trả danh sách RỖNG (không báo lỗi)
# Page có token Pancake (biến token trong .env, page_id, tên ngắn) và tên sale Pancake → người tạo đơn trên Nhanh:
# config/doanh_nghiep.yaml → pancake.pages / pancake.nv_nhanh. Public API của Pancake trả order_count = 0 nên số
# đơn lấy từ Nhanh (đơn tạo trong kỳ, bỏ huỷ — giống /nhanvien).
PAGES = [(p["token_env"], str(p["id"]), p["ten"]) for p in (cau_hinh.lay("pancake.pages") or [])]
NV_NHANH = dict(cau_hinh.lay("pancake.nv_nhanh") or {})
CACHE = fb.ROOT / "data" / "pancake_tin_nhan_ngay.json"
CHOT_SAU = 3 * 3600             # giây sau nửa đêm — ngày được tính sau mốc này thì coi là chốt, không tính lại
KHOA_FILE = CACHE.with_suffix(".lock")   # đang tính nhiều ngày (chạy bù) — lệnh tháng khác chờ, khỏi tính trùng
_GIOI_HAN = threading.BoundedSemaphore(LUONG)
_KHOA_CACHE = threading.Lock()


class DangTinh(RuntimeError):
    """Tiến trình khác đang tính bù nhiều ngày — báo người gõ lệnh thử lại sau."""


def _giu_khoa() -> None:
    try:
        bat_dau = float(KHOA_FILE.read_text(encoding="utf-8"))
        if time.time() - bat_dau < 4 * 3600:
            raise DangTinh(f"Đang tính số liệu tin nhắn nhiều ngày (bắt đầu {datetime.fromtimestamp(bat_dau):%H:%M}) "
                           "— gõ lại sau ít phút.")
    except (OSError, ValueError):
        pass
    KHOA_FILE.write_text(str(time.time()), encoding="utf-8")


def _goi(path: str, params: dict) -> dict:
    loi = ""
    for lan in range(5):
        try:
            with _GIOI_HAN:
                r = requests.get(f"{API}/{path}", params=params, timeout=90)
            if r.status_code == 200:
                j = r.json()
                if j.get("success") is not False:
                    return j
                loi = str(j.get("message"))[:200]
            else:
                loi = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as e:
            loi = type(e).__name__
        time.sleep(2 * (lan + 1))
    raise RuntimeError(f"Pancake lỗi ({path.split('/')[1]}): {loi}")


def _ts(s: str | None) -> float:
    """Giờ Pancake là UTC, không có hậu tố Z."""
    return datetime.fromisoformat(s[:19]).replace(tzinfo=timezone.utc).timestamp() if s else 0.0


def _dau_ngay(d: date) -> float:
    return datetime(d.year, d.month, d.day, tzinfo=VN).timestamp()


def _ngay_cua(t: float) -> str:
    return datetime.fromtimestamp(t, VN).date().isoformat()


def hoi_thoai_cap_nhat(pid: str, tok: str, tu: float) -> list[dict]:
    """Hội thoại INBOX có cập nhật từ `tu` tới giờ.

    Không lật trang (page_number 2, 3…): khách nhắn trong lúc đang tải làm hội thoại nhảy khỏi khung → các trang sau
    bị dồn, sót hội thoại (thử 05/10: lật trang song song sót 15%). Thay vào đó chia khung giờ cập nhật đến khi mỗi
    khung ≤ 200 hội thoại (1 trang); hội thoại cập nhật trong lúc tải chỉ dịch về phía "bây giờ" nên lấy lại khung
    cuối (từ mốc tới lúc tải xong) sau cùng. API chỉ cho until − since ≤ 1 tháng → khung đầu tối đa 25 ngày.
    """
    def khung(a: int, b: int) -> tuple[list[dict], list[tuple[int, int]]]:
        for lan in range(4):
            j = _goi(f"pages/{pid}/conversations", {"page_access_token": tok, "since": a, "until": b,
                                                     "page_number": 1, "order_by": "updated_at"})
            n = int(j.get("total") or 0)
            if not n or j.get("conversations"):
                break
            time.sleep(5 * (lan + 1))   # có tổng mà danh sách rỗng = bị gọi dồn
        if n <= 200 or b - a < 60:
            return j.get("conversations") or [], []
        k = math.ceil(n / 150)   # chia đều theo thời gian, dư chỗ vì hội thoại không rải đều
        buoc = (b - a) / k
        return [], [(int(a + i * buoc) + (i > 0), int(a + (i + 1) * buoc) if i < k - 1 else b) for i in range(k)]

    def tai(khoang: list[tuple[int, int]]) -> list[dict]:
        out = []
        with ThreadPoolExecutor(LUONG) as ex:
            dang = {ex.submit(khung, a, b) for a, b in khoang}
            while dang:
                xong, dang = wait(dang, return_when=FIRST_COMPLETED)
                for f in xong:
                    cs, chia = f.result()
                    out += cs
                    dang |= {ex.submit(khung, a, b) for a, b in chia}
        return out

    for lan in range(3):
        moc = int(time.time())
        a, khoang = int(tu), []
        while a <= moc:
            khoang.append((a, min(a + 25 * NGAY, moc)))
            a += 25 * NGAY + 1
        # tổng Pancake báo cho từng khung lớn — để kiểm tra không bị sót (Pancake đôi khi trả rỗng khi bị gọi dồn)
        can = sum(int(_goi(f"pages/{pid}/conversations", {"page_access_token": tok, "since": x, "until": y,
                                                          "page_number": 1, "order_by": "updated_at"}).get("total") or 0)
                  for x, y in khoang)
        ds = tai(khoang)
        if len({c["id"] for c in ds}) >= can * 0.98:
            break
        print(f"[pancake] page {pid}: lấy được {len(ds)}/{can} hội thoại — thử lại", file=sys.stderr)
        time.sleep(30)
    else:
        raise RuntimeError(f"Pancake trả thiếu hội thoại ({len(ds)}/{can}) — thử lại sau")
    ds += tai([(moc + 1, int(time.time()) + 60)])
    gap = {c["id"]: c for c in ds if c.get("type") == "INBOX"}   # trùng (vừa cập nhật lúc tải) thì lấy bản sau
    return list(gap.values())


def _bam_qc(ds) -> list[float]:
    return [_ts(a.get("inserted_at")) for a in (ds or []) if a and a.get("inserted_at")]


def _tin_nhan(pid: str, tok: str, cid: str, can_tu: float) -> tuple[list[dict], dict]:
    """Tin nhắn mới nhất → lùi trang (30 tin/lần) tới khi có tin cũ hơn `can_tu` (tối đa 20 lần)."""
    ms, dau = [], None
    for _ in range(20):
        p = {"page_access_token": tok}
        if ms:
            p["current_count"] = len(ms)
        for lan in range(3):
            j = _goi(f"pages/{pid}/conversations/{cid}/messages", p)
            if ms or j.get("messages"):
                break
            time.sleep(5 * (lan + 1))   # hội thoại có QC mà không có tin nào = Pancake trả rỗng khi bị gọi dồn
        else:
            raise RuntimeError("Pancake trả tin nhắn rỗng")
        dau = dau or j
        moi = [m for m in j.get("messages") or [] if m]
        ms = moi + ms
        if len(moi) < 30 or min(_ts(m.get("inserted_at")) for m in moi) < can_tu:
            break
    return ms, dau


def _xet(pid: str, tok: str, c: dict, t0: float, t1: float) -> list[tuple[str, str | None, bool]]:
    """1 hội thoại → [(ngày, người trả lời đầu | None, có nhiều người nhắn)] cho mỗi lần bắt đầu từ QC trong [t0, t1)."""
    bam_ht = [t for t in _bam_qc(c.get("ads")) if t0 <= t < t1]
    if not bam_ht:
        return []
    ms, j = _tin_nhan(pid, tok, c["id"], min(bam_ht) - TUAN)
    bam = bam_ht + _bam_qc([a for v in (j.get("ad_clicks") or {}).values() for a in (v or [])])
    bam += [_ts(a.get("inserted_at")) for a in j.get("activities") or []
            if a and a.get("source") == "ADS" and a.get("type") == "OPEN_THREAD"]
    ms = [m for m in ms if m.get("from")]
    khach = [_ts(m.get("inserted_at")) for m in ms if m["from"].get("id") != pid]
    nv = sorted((_ts(m.get("inserted_at")), m["from"].get("admin_name") or m["from"]["uid"])
                for m in ms if m["from"].get("id") == pid and m["from"].get("uid"))
    # FB chỉ tính "bắt đầu trò chuyện" khi khách im lặng >= 7 ngày; bỏ 2 phút sát lần bấm (tin mẫu gửi kèm)
    bd = []
    for t in sorted(set(t for t in bam if t0 <= t < t1)):
        if (not bd or t - bd[-1] > 120) and not any(t - TUAN <= k < t - 120 for k in khach):
            bd.append(t)
    out = []
    for i, t in enumerate(bd):
        het = bd[i + 1] if i + 1 < len(bd) else float("inf")
        ten = list(dict.fromkeys(n for tm, n in nv if t - 60 <= tm < het))
        out.append((_ngay_cua(t), ten[0] if ten else None, len(ten) > 1))
    return out


def _rong() -> dict:
    return {"hoi_thoai": 0, "nv": {}, "khong_tl": 0, "nhieu_nv": 0, "loi": 0}


def dem_khoang(pid: str, tok: str, d0: date, d1: date) -> dict[str, dict]:
    """{ngày ISO: số liệu} cho từng ngày trong [d0, d1] của 1 page."""
    t0, t1 = _dau_ngay(d0), _dau_ngay(d1) + NGAY
    ung_vien = [c for c in hoi_thoai_cap_nhat(pid, tok, t0) if any(t0 <= t < t1 for t in _bam_qc(c.get("ads")))]
    kq = {(d0 + timedelta(days=i)).isoformat(): _rong() for i in range((d1 - d0).days + 1)}
    with ThreadPoolExecutor(LUONG) as ex:
        viec = {ex.submit(_xet, pid, tok, c, t0, t1): c for c in ung_vien}
        for f, c in viec.items():
            try:
                ev = f.result()
            except RuntimeError:
                kq[_ngay_cua(min(t for t in _bam_qc(c.get("ads")) if t0 <= t < t1))]["loi"] += 1
                continue
            for ngay, ten, nhieu in ev:
                x = kq[ngay]
                x["hoi_thoai"] += 1
                if ten:
                    x["nv"][ten] = x["nv"].get(ten, 0) + 1
                    x["nhieu_nv"] += nhieu
                else:
                    x["khong_tl"] += 1
    return kq


def _doc_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _chot(ngay: str, v: dict) -> bool:
    return v.get("luc", 0) >= _dau_ngay(date.fromisoformat(ngay)) + NGAY + CHOT_SAU


def so_lieu(d0: date, d1: date) -> list[dict]:
    """Tổng [d0, d1] theo page (page có token). Ngày đã chốt lấy từ cache; ngày thiếu thì tính rồi lưu."""
    out = []
    for bien, pid, ten in PAGES:
        tok = os.getenv(bien, "").strip()
        if not tok:
            continue
        ngay = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
        co = _doc_cache().get(pid, {})
        thieu = [n for n in ngay if not (n in co and _chot(n, co[n]))]
        if thieu:
            nhieu_ngay = len(thieu) >= 3
            if nhieu_ngay:
                _giu_khoa()
            try:
                moi = dem_khoang(pid, tok, date.fromisoformat(thieu[0]), date.fromisoformat(thieu[-1]))
            finally:
                if nhieu_ngay:
                    KHOA_FILE.unlink(missing_ok=True)
            luc = time.time()
            with _KHOA_CACHE:
                tat = _doc_cache()
                tat.setdefault(pid, {}).update({k: {**v, "luc": luc} for k, v in moi.items()})
                tam = CACHE.with_suffix(".tmp")
                tam.write_text(json.dumps(tat, ensure_ascii=False), encoding="utf-8")
                tam.replace(CACHE)
            co = tat[pid]
        tong = {**_rong(), "page": ten}
        for n in ngay:
            v = co.get(n) or _rong()
            for k in ("hoi_thoai", "khong_tl", "nhieu_nv", "loi"):
                tong[k] += v[k]
            for k, s in v["nv"].items():
                tong["nv"][k] = tong["nv"].get(k, 0) + s
        out.append(tong)
    return out


def don_nhanh(d0: date, d1: date) -> dict[str, int] | None:
    """Số đơn (bỏ huỷ) theo người tạo đơn trên Nhanh — {tên Nhanh: số đơn}; lỗi Nhanh thì None."""
    import bao_cao_ads_telegram as bc
    try:
        return {x["ten"]: x["don"] for x in bc.so_lieu_nhanh_cache(d0.isoformat(), d1.isoformat())["nv"]}
    except Exception:  # noqa: BLE001 — thiếu số đơn thì vẫn gửi phần hội thoại
        return None


def tro_chuyen_fb(d0: date, d1: date) -> float | None:
    """Tổng lượt bắt đầu trò chuyện Facebook báo (mọi tài khoản QC) — để đối chiếu."""
    import bao_cao_ads_telegram as bc
    try:
        return sum(r["tc"] for r in bc.lay_so_lieu(d0.isoformat(), d1.isoformat()))
    except Exception:  # noqa: BLE001 — chỉ là dòng đối chiếu, lỗi Meta không chặn báo cáo
        return None


def _so(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def _pt(n: float, tong: float) -> str:
    return "&lt;1%" if 0 < n / tong < 0.005 else f"{n / tong:.0%}"


def _tl(don: float, ht: float) -> str:
    return f"{don / ht:.1%}".replace(".", ",") if ht else "—"


def soan_tin(pages: list[dict], nhan: str, fb_tc: float | None, don: dict[str, int] | None = None) -> str:
    e = html.escape
    tong = sum(p["hoi_thoai"] for p in pages)
    nv: dict[str, int] = {}
    for p in pages:
        for k, v in p["nv"].items():
            nv[k] = nv.get(k, 0) + v
    khong = sum(p["khong_tl"] for p in pages)
    nhieu = sum(p["nhieu_nv"] for p in pages)
    loi = sum(p["loi"] for p in pages)
    dong = [f"💬 <b>Hội thoại từ quảng cáo theo nhân viên — {e(nhan)}</b>"]
    if fb_tc is not None:
        dong.append(f"Facebook báo: <b>{_so(fb_tc)}</b> lượt bắt đầu trò chuyện")
    co = [p for p in pages if p["hoi_thoai"]]
    dong.append(f"Pancake ghi nhận: <b>{_so(tong)}</b>"
                + (" (" + " · ".join(f"{e(p['page'])} {_so(p['hoi_thoai'])}" for p in co) + ")" if co else ""))
    if tong:
        dong += ["", "<b>Người trả lời đầu tiên:</b>"]
        tong_don = 0
        for ten, n in sorted(nv.items(), key=lambda x: -x[1]):
            dn = don.get(NV_NHANH.get(ten, ""), 0) if don is not None else None
            chot = f" · {_so(dn)} đơn · chốt <b>{_tl(dn, n)}</b>" if dn is not None and ten in NV_NHANH else ""
            tong_don += dn or 0
            dong.append(f"• {e(ten)}: <b>{_so(n)}</b> HT ({_pt(n, tong)}){chot}")
        if khong:
            dong.append(f"• Chưa có nhân viên trả lời (chỉ bot): <b>{_so(khong)}</b> ({_pt(khong, tong)})")
        if don is not None:
            dong.append(f"<b>Tỷ lệ chốt chung: {_tl(tong_don, tong)}</b> ({_so(tong_don)} đơn / {_so(tong)} hội thoại)")
        else:
            dong.append("⚠️ Không lấy được số đơn từ Nhanh — chưa tính tỷ lệ chốt.")
        dong += ["", "<i>Tính cho người nhắn đầu tiên sau khi khách bấm QC"
                     + (f" ({_so(nhieu)} hội thoại có nhiều người cùng nhắn)" if nhieu else "")
                     + "; chỉ tính khách im lặng ≥7 ngày như cách FB đếm. HT = hội thoại. Tỷ lệ chốt = đơn Nhanh "
                       "(người tạo đơn, bỏ huỷ, mọi nguồn) / hội thoại từ QC.</i>"]
    if loi:
        dong.append(f"⚠️ {_so(loi)} hội thoại không đọc được từ Pancake (bỏ qua).")
    return "\n".join(dong)


def bao_cao(d0: date, d1: date, nhan: str) -> str:
    return soan_tin(so_lieu(d0, d1), nhan, tro_chuyen_fb(d0, d1), don_nhanh(d0, d1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tu", help="YYYY-MM-DD (mặc định hôm qua)")
    ap.add_argument("--den", help="YYYY-MM-DD (mặc định = --tu)")
    ap.add_argument("--bu", action="store_true", help="tính + lưu các ngày chưa chốt từ đầu tháng trước tới hôm qua")
    a = ap.parse_args()
    t = time.time()
    hq = date.today() - timedelta(days=1)
    if a.bu:
        d0 = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
        kq = so_lieu(d0, hq)
        print(f"[{datetime.now():%d/%m %H:%M}] bù {d0:%d/%m}–{hq:%d/%m}: "
              + ", ".join(f"{p['page']} {p['hoi_thoai']}" for p in kq) + f" ({time.time() - t:.0f} giây)")
        return
    d0 = date.fromisoformat(a.tu) if a.tu else hq
    d1 = date.fromisoformat(a.den) if a.den else d0
    print(bao_cao(d0, d1, f"{d0:%d/%m}" + (f"–{d1:%d/%m}" if d1 != d0 else "")))
    print(f"({time.time() - t:.0f} giây)", file=sys.stderr)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
