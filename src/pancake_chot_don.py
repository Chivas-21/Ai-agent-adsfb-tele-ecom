"""Đơn + doanh số sale đã chốt trên Pancake, đọc từ nội dung hội thoại (theo ngày chọn).

Chủ trang (13/10/2026): "báo cáo đơn và doanh số đã chốt ở trên Pancake bằng việc đọc hội thoại để biết đoạn hội thoại
đó các bạn sale tư vấn đã chốt khách" — chọn cách chỉ đọc chữ trong chat (không ghép đơn Nhanh), xem qua lệnh bot
/chotdon theo ngày chọn.

Cách nhận ra 1 đơn chốt: tin của nhân viên (có uid — không tính Botcake) trong ngày là tin xác nhận đơn. Sale dùng mẫu
"Dạ em xin gửi lại thông tin đơn hàng để mình xác nhận ạ: - Thông tin sp: … - Tổng giá trị đơn hàng (kèm ship): 399K",
hoặc gõ tay "dạ thông tin đơn … Tổng 546 + 30 ship", "tổng đơn 619 miễn ship", "em chốt đơn …"; Lan Anh gõ
"Dạ e gửi chị / 1 váy Remy be kem L 369k / 3 áo A10 XL 199k*3 / = 966k freship", "… 399+ 30k ship = 429k nhé".
Tin mời mua (có "chất liệu", "giá gốc", "giảm còn"…) hoặc dài > 700 ký tự không tính.
- Chỉ đọc hội thoại được sale gắn thẻ Done/CLĐ trong ngày (thẻ chỉ để chọn hội thoại, căn cứ vẫn là chữ trong tin) —
  xem don_ngay; --quet-het đọc mọi hội thoại để đối chiếu (~11 phút/ngày).
- Số tiền: số sau dấu "=" hoặc chữ "tổng" (cộng thêm "+ 30 ship" nếu sale ghi riêng); không có thì cộng giá từng dòng
  sản phẩm (349K, 99*2…) + ship. Số < 10.000 hiểu là nghìn đồng.
- Sale gửi lại tin xác nhận khi khách thêm/đổi món → 1 hội thoại chỉ tính 1 đơn, lấy tin xác nhận CUỐI; hai lần xác nhận
  cách nhau > 12 giờ thì tính 2 đơn. Gán cho người gửi tin xác nhận cuối.
- Không biết đơn có bị huỷ/hoàn sau đó — đây là số chốt trong chat, không phải doanh thu Nhanh.

Ngày đã qua (≥3 giờ sáng hôm sau) được lưu ở data/pancake_chot_don_ngay.json, gõ lại không phải đọc lại Pancake.

    python src/pancake_chot_don.py                    # hôm qua
    python src/pancake_chot_don.py --ngay 2026-10-12 [--chi-tiet] [--quet-het]
"""
import argparse
import html
import json
import os
import re
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import pancake_tin_nhan as pk

CACHE = pk.fb.ROOT / "data" / "pancake_chot_don_ngay.json"
_KHOA_CACHE = threading.Lock()
TACH_DON = 12 * 3600    # 2 tin xác nhận trong 1 hội thoại cách nhau hơn thế = 2 đơn
THE_CHOT = tuple(pk.cau_hinh.lay("pancake.the_chot") or ("Done", "CLĐ"))   # thẻ Pancake: "KH đã chốt đơn … đã/chưa lên đơn trên Nhanh"

# tin xác nhận đơn (đã chuẩn hoá NFKC + chữ thường) — "chốt đơn từ 800k" trong tin quảng bá không khớp
CHOT = re.compile(r"thông tin đơn|tổng\b[^\n]{0,40}?(?<![\w.,])(?:\d{1,3}(?:[.,]\d{3})+|\d{3,}|\d[\d.,]*\d\s*k)"   # "tổng 2 bộ 798 miẽn ship"
                  r"|em chốt đơn|chốt đơn\s*:|chốt (?:của|cho) (?:chị|c|anh|a|mình)"
                  r"|(?:\d\s*k?\s*(?:[*x]\s*\d+\s*)?(?:\+\s*\d+\s*k?\s*(?:ship|sip)\s*)?|\n\s*)=\s*\d[\d.,]*\d")   # "399k+ 30k ship= 429k"
# kiểu Lan Anh: "Dạ e gửi chị / 1 váy Remy be kem L 369k / 3 áo A10 XL 199k*3 / = 966k freship"
GUI = re.compile(r"(?:em|e)\s+(?:xin\s+)?gửi\s+(?:lại\s+)?(?:chị|c|anh|a|mình|bạn)(?:\s+(?:thêm|yêu))?\s*:?\s*\n")
CO_GIA = re.compile(r"\d{2,4}\s*k(?![a-zà-ỹ])|\d{2,4}\s*[*x]\s*\d")
QUANG_BA = re.compile(r"chất liệu|giá gốc|sale up to|giảm còn|đang sale|ưu đãi hấp dẫn|mã giảm"   # tin mời mua, không phải chốt
                      r"|phí đổi|đổi hàng")   # phí đổi size/đổi hàng ("đổi hàng mỗi chiều 30k tổng 60k")
_TONG = re.compile(r"tổng\b[^\n]{0,40}?(?<![\w.,])(\d[\d.,]*\d)\s*(?:(vnđ|vnd|k|đ|d)|(?![a-zà-ỹ]))"
                   r"(?:\s*\+\s*(\d[\d.,]*)\s*k?\s*(?:ship|sip|phí ship))?")
_BANG = re.compile(r"=\s*(\d[\d.,]*\d)\s*(?:(k|đ|d)|(?![a-zà-ỹ]))")   # "250k + 30k ship = 280k"
_SHIP = re.compile(r"\+\s*(\d[\d.,]*)\s*k?\s*(?:ship|sip)")
_GIA = re.compile(r"(?<![\w.,])(\d{2,4}(?:[.,]\d{3})*)\s*(k|đ|d)?(?![a-zà-ỹ\d])(?:\s*[*x×]\s*(\d{1,2})(?![\w]))?"
                  r"(?!\s*k?\s*(?:ship|sip))")


def _chuan(s: str) -> str:
    """Chữ in đậm kiểu 𝟐𝟗𝟗𝐊 → 299k; chữ thường."""
    return unicodedata.normalize("NFKC", s or "").lower()


def _dong(so: str, don_vi: str | None = None) -> float:
    v = float(re.sub(r"[.,]", "", so)) if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", so) else float(so.replace(",", "."))
    return v if v >= 10000 or don_vi in ("đ", "d", "vnđ", "vnd") and v >= 1000 else v * 1000


def so_tien(tin: str) -> float | None:
    """Tiền của 1 tin xác nhận đơn (đồng) — None nếu không đọc được."""
    t = _chuan(tin)
    tong = list(_TONG.finditer(t))
    bang = list(_BANG.finditer(t))
    if bang and (not tong or bang[-1].start() > tong[-1].start()):
        con = re.search(r"còn\s*(\d[\d.,]*\d)\s*(?:(k|đ|d)|(?![a-zà-ỹ]))", t[bang[-1].end():])   # "= 798k ưu đãi còn 789k"
        m = con or bang[-1]
        v = _dong(m.group(1), m.group(2))
        return v if v >= 30000 else None
    if tong:
        m = tong[-1]
        v = _dong(m.group(1), m.group(2))
        if m.group(3) and "kèm ship" not in m.group(0):
            v += _dong(m.group(3))
        return v if v >= 30000 else None
    i = max(t.find("thông tin sp"), t.find("thông tin đơn"), 0)
    phan = re.split(r"chị chú ý|c chú ý", t[i:])[0]
    gia = [_dong(m.group(1), m.group(2)) * int(m.group(3) or 1) for m in _GIA.finditer(phan)]
    gia = [g for g in gia if g >= 50000]
    if not gia:
        return None
    return sum(gia) + sum(_dong(m.group(1)) for m in _SHIP.finditer(phan))


def _la_chot(tin: str) -> bool:
    t = _chuan(tin)
    if len(t) > 700 or QUANG_BA.search(t):
        return False
    if CHOT.search(t):
        return True
    g = GUI.search(t)
    return bool(g and CO_GIA.search(t[g.end():]))


def _don_hoi_thoai(pid: str, tok: str, c: dict, t0: float, t1: float, page: str) -> list[dict]:
    ms, _ = pk._tin_nhan(pid, tok, c["id"], t0)
    xn = sorted((pk._ts(m.get("inserted_at")), m["from"].get("admin_name") or m["from"]["uid"],
                 m.get("original_message") or m.get("message") or "")
                for m in ms if (m.get("from") or {}).get("id") == pid and m["from"].get("uid")
                and t0 <= pk._ts(m.get("inserted_at")) < t1 and _la_chot(m.get("original_message") or m.get("message") or ""))
    don: list[list] = []
    for x in xn:
        if don and x[0] - don[-1][-1][0] <= TACH_DON:
            don[-1].append(x)
        else:
            don.append([x])
    kh = ((c.get("customers") or [{}])[0] or {}).get("name") or (c.get("from") or {}).get("name") or ""
    # SĐT khách: Pancake tự tách (recent_phone_numbers) + số khách gõ trong tin ("0972 659 468") — để đối chiếu Nhanh
    sdt = {_sdt(p.get("phone_number") or p.get("captured")) for p in c.get("recent_phone_numbers") or [] if p}
    sdt |= {_sdt(x) for m in ms if (m.get("from") or {}).get("id") != pid
            for x in _SO_DT.findall(m.get("original_message") or m.get("message") or "")}
    sdt.discard("")
    the = [t["text"] for t in c.get("tags") or [] if t and t.get("text") in THE_CHOT]
    return [{"page": page, "cid": c["id"], "kh": kh, "nv": d[-1][1], "luc": d[-1][0], "tien": so_tien(d[-1][2]),
             "tin": d[-1][2][:400], "so_lan": len(d), "sdt": sorted(sdt), "the": the} for d in don]


_SO_DT = re.compile(r"(?<!\d)(?:\+?84|0)(?:[\s.]?\d){9}(?!\d)")


def _sdt(s: str | None) -> str:
    """Chuẩn hoá SĐT → 9 số cuối ('' nếu không phải SĐT VN)."""
    so = re.sub(r"\D", "", s or "")
    return so[-9:] if len(so) >= 9 else ""


POS_API = "https://pos.pages.fm/api/v1"


def sdt_pos(d: date) -> tuple[set[str] | None, str]:
    """SĐT khách của đơn Pancake POS tạo từ đầu ngày d tới giờ → (tập SĐT | None nếu chưa cấu hình/lỗi, lý do).

    Cần config/.env: PANCAKE_POS_API_KEY + PANCAKE_POS_SHOP_ID (nhiều shop: cách nhau dấu phẩy) — chủ trang lấy ở
    Pancake POS → Cấu hình → Ứng dụng → API KEY (13/10/2026: sale có thể lên đơn ở POS thay vì Nhanh).
    """
    import requests
    key = os.getenv("PANCAKE_POS_API_KEY", "").strip()
    shops = [s.strip() for s in os.getenv("PANCAKE_POS_SHOP_ID", "").split(",") if s.strip()]
    if not key or not shops:
        return None, "chưa cấu hình"
    t0, t1 = int(pk._dau_ngay(d)), int(time.time())
    out: set[str] = set()
    try:
        for shop in shops:
            for trang in range(1, 101):
                r = requests.get(f"{POS_API}/shops/{shop}/orders", timeout=60, params={
                    "api_key": key, "page_number": trang, "page_size": 200, "startDateTime": t0, "endDateTime": t1})
                j = r.json()
                if r.status_code != 200 or j.get("success") is False:
                    return None, f"shop {shop}: {str(j.get('message') or r.status_code)[:80]}"
                ds = j.get("data") or []
                for o in ds:
                    sa = o.get("shipping_address") or {}
                    for so in (o.get("bill_phone_number"), sa.get("phone_number"),
                               *((o.get("customer") or {}).get("phone_numbers") or [])):
                        out.add(_sdt(so if isinstance(so, str) else str(so or "")))
                if trang >= int(j.get("total_pages") or 1) or not ds:
                    break
    except (requests.RequestException, ValueError) as e:
        return None, type(e).__name__
    return out - {""}, ""


def sdt_nhanh(d: date) -> set[str] | None:
    """SĐT người nhận của mọi đơn Nhanh tạo từ đầu ngày d tới giờ (kể cả đơn đã huỷ — đã lên đơn rồi); lỗi → None."""
    try:
        from nhanh_client import NhanhClient
        t0 = datetime.fromtimestamp(pk._dau_ngay(d), pk.VN)
        return {_sdt((o.get("shippingAddress") or {}).get("mobile")) for o in NhanhClient().list_orders(t0, datetime.now(pk.VN))} - {""}
    except Exception:  # noqa: BLE001 — Nhanh lỗi thì vẫn gửi phần đơn chốt, chỉ thiếu mục chưa lên đơn
        return None


def _gan_the_chot(c: dict, t0: float, t1: float) -> bool:
    """Sale gắn thẻ Done / CLĐ (KH đã chốt đơn) cho hội thoại trong [t0, t1)."""
    return any(t0 <= pk._ts(h.get("inserted_at")) < t1 and (h.get("payload") or {}).get("action") == "add"
               and ((h["payload"].get("tag") or {}).get("text") in THE_CHOT) for h in c.get("tag_histories") or [])


def don_ngay(pid: str, tok: str, d: date, page: str, quet_het: bool = False) -> tuple[list[dict], int]:
    """(đơn chốt trong ngày d của 1 page, số hội thoại đọc lỗi).

    Mặc định chỉ đọc tin của hội thoại được gắn thẻ Done/CLĐ trong ngày (~60 thay vì ~3.700 hội thoại/ngày, vài giây
    thay vì 11 phút) — đo 12/10/2026: quét hết 3.768 hội thoại ra 45 đơn, cả 45 đều nằm trong nhóm có thẻ. Chữ trong
    tin vẫn là căn cứ chốt đơn và số tiền; thẻ chỉ để chọn hội thoại cần đọc. `quet_het` = đọc mọi hội thoại (đối chiếu).
    """
    t0 = pk._dau_ngay(d)
    t1 = t0 + pk.NGAY
    ds = [c for c in pk.hoi_thoai_cap_nhat(pid, tok, t0) if pk._ts(c.get("updated_at")) >= t0
          and (quet_het or _gan_the_chot(c, t0, t1))]
    out, loi = [], 0
    with ThreadPoolExecutor(pk.LUONG) as ex:
        for f in [ex.submit(_don_hoi_thoai, pid, tok, c, t0, t1, page) for c in ds]:
            try:
                out += f.result()
            except RuntimeError:
                loi += 1
    return sorted(out, key=lambda x: x["luc"]), loi


def _doc_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def so_lieu(d: date, quet_het: bool = False) -> dict:
    """{"don": [...], "loi": n, "pages": [tên page đã đọc]} của ngày d — ngày đã chốt lấy từ cache."""
    k = d.isoformat()
    co = _doc_cache().get(k)
    if co and pk._chot(k, co) and not quet_het:
        return co
    kq = {"don": [], "loi": 0, "pages": []}
    for bien, pid, ten in pk.PAGES:
        tok = os.getenv(bien, "").strip()
        if not tok:
            continue
        don, loi = don_ngay(pid, tok, d, ten, quet_het)
        kq["don"] += don
        kq["loi"] += loi
        kq["pages"].append(ten)
    kq["luc"] = time.time()
    with _KHOA_CACHE:
        tat = _doc_cache()
        tat[k] = kq
        tam = CACHE.with_suffix(".tmp")
        tam.write_text(json.dumps(tat, ensure_ascii=False), encoding="utf-8")
        tam.replace(CACHE)
    return kq


def _tr(v: float) -> str:
    return pk._so(v) + "đ"


def _chua_len(x: dict, sdt_nh: set[str] | None) -> bool | None:
    """Đơn chốt chưa có trên Nhanh? None = không đối chiếu được (Nhanh lỗi / hội thoại không có SĐT)."""
    if sdt_nh is None or not x.get("sdt"):
        return None
    return not (set(x["sdt"]) & sdt_nh)


def soan_tin(kq: dict, nhan: str, don_nv: dict[str, int] | None = None, chi_tiet: bool = False,
             sdt_nh: set[str] | None = None, tu_ngay: str = "", nguon: str = "Nhanh", canh_bao_pos: str = "") -> str:
    e = html.escape
    don = kq["don"]
    dong = [f"🛒 <b>Đơn chốt trong hội thoại Pancake — {e(nhan)}</b>"]
    if not don:
        dong.append("Không thấy tin xác nhận đơn nào của sale.")
    else:
        tien = [x["tien"] for x in don if x["tien"]]
        tong = sum(tien)
        theo_page: dict[str, int] = {}
        for x in don:
            theo_page[x["page"]] = theo_page.get(x["page"], 0) + 1
        dong.append(f"Tổng: <b>{pk._so(len(don))} đơn</b> · <b>{_tr(tong)}</b>"
                    + (f" · TB {_tr(tong / len(tien))}/đơn" if tien else ""))
        if len(theo_page) > 1:
            dong.append(" · ".join(f"{e(p)} {pk._so(n)}" for p, n in sorted(theo_page.items(), key=lambda x: -x[1])))
        nv: dict[str, list] = {}
        for x in don:
            nv.setdefault(x["nv"], []).append(x)
        dong += ["", "<b>Theo sale (người gửi tin xác nhận):</b>"]
        for ten, ds in sorted(nv.items(), key=lambda x: -sum(d["tien"] or 0 for d in x[1])):
            t = sum(d["tien"] or 0 for d in ds)
            nh = don_nv.get(pk.NV_NHANH.get(ten, "")) if don_nv is not None and ten in pk.NV_NHANH else None
            dong.append(f"• {e(ten)}: <b>{pk._so(len(ds))} đơn</b> · <b>{_tr(t)}</b>"
                        + (f" ({_pt(t, tong)})" if tong else "")
                        + (f" · Nhanh {pk._so(nh)} đơn" if nh is not None else ""))
        for ten, ten_nh in pk.NV_NHANH.items():
            if ten not in nv and don_nv and don_nv.get(ten_nh):
                dong.append(f"• {e(ten)}: <b>0 đơn</b> · Nhanh {pk._so(don_nv[ten_nh])} đơn")
        thieu = len(don) - len(tien)
        if thieu:
            dong.append(f"⚠️ {pk._so(thieu)} đơn không đọc được số tiền trong tin (đã đếm đơn, chưa cộng tiền).")
        if sdt_nh is None:
            dong += ["", f"⚠️ Không lấy được đơn {nguon} — chưa kiểm tra được đơn nào chưa lên."]
        else:
            chua = sorted((x for x in don if _chua_len(x, sdt_nh)), key=lambda x: x["luc"])
            ko_sdt = [x for x in don if _chua_len(x, sdt_nh) is None]
            dong += ["", f"⏳ <b>Đã chốt nhưng chưa lên đơn {nguon}: {pk._so(len(chua))} đơn</b>"
                         + (f" · <b>{_tr(sum(x['tien'] or 0 for x in chua))}</b>" if chua else "")]
            if canh_bao_pos:
                dong.append(canh_bao_pos)
            for x in chua[:40]:
                gio = datetime.fromtimestamp(x["luc"], pk.VN).strftime("%H:%M")
                dong.append(f"• {gio} {e(x['nv'])} · {e(x['kh'] or '?')} · "
                            + (_tr(x["tien"]) if x["tien"] else "?") + f" · SĐT …{x['sdt'][0][-4:]}"
                            + (f" · thẻ {'/'.join(x['the'])}" if x.get("the") else ""))
            if len(chua) > 40:
                dong.append(f"… và {pk._so(len(chua) - 40)} đơn nữa")
            if ko_sdt:
                dong.append(f"<i>{pk._so(len(ko_sdt))} đơn không có SĐT trong hội thoại nên chưa đối chiếu được: "
                            + ", ".join(e(x["kh"] or "?") + f" ({e(x['nv'])})" for x in ko_sdt[:15]) + "</i>")
        if chi_tiet:
            dong += ["", "<b>Chi tiết:</b>"]
            for x in sorted(don, key=lambda x: x["luc"]):
                gio =datetime.fromtimestamp(x["luc"], pk.VN).strftime("%H:%M")
                dong.append(f"{gio} {e(x['nv'])} · {e(x['kh'] or '?')} · "
                            + (_tr(x["tien"]) if x["tien"] else "?") + f" ({e(x['page'])})")
    if kq.get("loi"):
        dong.append(f"⚠️ {pk._so(kq['loi'])} hội thoại không đọc được từ Pancake (bỏ qua).")
    dong += ["", "<i>Đếm 1 đơn khi sale gửi tin báo đơn (\"thông tin đơn hàng…\", \"tổng đơn…\", \"e gửi chị … = 429k\") "
                 "trong hội thoại được gắn thẻ Done/CLĐ; tiền lấy ở tin báo đơn cuối, gồm ship nếu sale ghi. Chưa trừ đơn "
                 "huỷ/hoàn sau đó."
                 + (" Cột Nhanh = số đơn người đó tạo trên Nhanh cùng ngày (đối chiếu)." if don_nv is not None else "")
                 + (f" Chưa lên đơn = SĐT khách trong hội thoại không khớp đơn {nguon} nào tạo từ {tu_ngay} tới lúc gõ."
                    if sdt_nh is not None else "")
                 + "</i>"]
    return "\n".join(dong)


def _pt(n: float, tong: float) -> str:
    return f"{n / tong:.0%}" if tong else "—"


def bao_cao(d: date, nhan: str, chi_tiet: bool = False, quet_het: bool = False) -> str:
    kq = so_lieu(d, quet_het)
    nh = sdt_nhanh(d)
    pos, ly_do = sdt_pos(d)
    if pos is None:   # POS chưa cấu hình / lỗi → chỉ đối chiếu Nhanh (đơn lên ở POS sẽ hiện là chưa lên)
        canh_bao = "" if ly_do == "chưa cấu hình" else f"⚠️ Không đọc được đơn Pancake POS ({ly_do}) — chỉ đối chiếu Nhanh."
        return soan_tin(kq, nhan, pk.don_nhanh(d, d), chi_tiet, nh, f"{d:%d/%m}", "Nhanh", canh_bao)
    return soan_tin(kq, nhan, pk.don_nhanh(d, d), chi_tiet, None if nh is None else nh | pos, f"{d:%d/%m}",
                    "POS + Nhanh")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ngay", help="YYYY-MM-DD (mặc định hôm qua)")
    ap.add_argument("--chi-tiet", action="store_true")
    ap.add_argument("--quet-het", action="store_true", help="đọc mọi hội thoại, không lọc thẻ Done/CLĐ (chậm, để đối chiếu)")
    a = ap.parse_args()
    t = time.time()
    d = date.fromisoformat(a.ngay) if a.ngay else date.today() - timedelta(days=1)
    print(bao_cao(d, f"ngày {d:%d/%m}", a.chi_tiet, a.quet_het))
    print(f"({time.time() - t:.0f} giây)", file=sys.stderr)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
