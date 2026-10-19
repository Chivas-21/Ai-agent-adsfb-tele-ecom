"""Báo cáo tài chính dạng HTML (1 file, mở bằng trình duyệt) — bot gửi vào nhóm Telegram dạng tệp.

Chủ trang (06/10/2026): "/baocaotaichinh tháng này, tháng trước có hỏi thêm có làm báo cáo lên HTML không" → sau
/baocaotaichinh thang|thangtruoc bot hỏi, gõ /html (trong 10 phút) thì gửi tệp này.
Số liệu dùng lại đúng bộ số vừa soạn tin (rows Ads FB, so_lieu_nhanh, cp_qc_san) — cùng công thức
bao_cao_ads_telegram.soan_tai_chinh: lãi = doanh thu − giá vốn − phí sàn − CP QC (FB + sàn); chưa trừ ship, lương…
Kèm top 10 sản phẩm cha tổng các kênh (top_sp_nhan_vien) và doanh thu sàn theo hạng mục (hang_muc_san).
"""
import html
from datetime import datetime

from bao_cao_ads_telegram import vnd
from nhanh_client import VN_TZ

e = html.escape


def _pt(x: float, dt: float) -> str:
    return f"{x / dt:.1%}".replace(".", ",") if dt else "—"


def _so(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def tinh(rows: list[dict], nh: dict, cp_san: dict | None) -> dict:
    """Gom số theo kênh — cùng công thức soan_tai_chinh."""
    rows = [r for r in rows if r["chi"] > 0]
    chi = sum(r["chi"] for r in rows)
    nv, bl, san = nh["nv"], nh["ban_le"], nh["san"]
    kenh = [{"ten": "Nhân viên online", "dt": sum(a["dt"] for a in nv), "gv": sum(a.get("gv", 0) for a in nv),
             "phi": 0.0, "qc": chi, "ghi_qc": "Ads FB"},
            {"ten": "Cửa hàng bán lẻ", "dt": sum(a["dt"] for a in bl), "gv": sum(a.get("gv", 0) for a in bl),
             "phi": 0.0, "qc": 0.0, "ghi_qc": ""}]
    for k in san:
        kenh.append({"ten": k["kenh"], "dt": k["dt"], "gv": k.get("gv", 0), "phi": k.get("phi", 0),
                     "qc": (cp_san or {}).get(k["kenh"]) or 0, "ghi_qc": "Shopee Ads" if k["kenh"] == "Shopee" else "GMV Max"})
    for k in kenh:
        k["lai"] = k["dt"] - k["gv"] - k["phi"] - k["qc"]
    tong = {x: sum(k[x] for k in kenh) for x in ("dt", "gv", "phi", "qc", "lai")}
    return {"kenh": kenh, "tong": tong, "chi_fb": chi, "rows": rows}


TEN_DN = (__import__("cau_hinh").lay("ten") or "").upper()   # tên doanh nghiệp (config/doanh_nghiep.yaml)

CSS = """
:root{--nen:#f6f7f9;--the:#fff;--chu:#1f2328;--mo:#656d76;--ke:#e5e7eb;--nhan:#0d6efd;--lai:#198754;--lo:#dc3545}
@media (prefers-color-scheme:dark){:root{--nen:#0d1117;--the:#161b22;--chu:#e6edf3;--mo:#8b949e;--ke:#30363d;--nhan:#58a6ff;--lai:#3fb950;--lo:#f85149}}
*{box-sizing:border-box}body{margin:0;background:var(--nen);color:var(--chu);font:15px/1.5 -apple-system,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:20px 16px 40px}h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px}
.mo{color:var(--mo);font-size:13px}.the{background:var(--the);border:1px solid var(--ke);border-radius:10px;padding:14px}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:16px}
.kpi .so{font-size:20px;font-weight:700;margin-top:2px}.kpi .lai .so{color:var(--lai)}
.bang{overflow-x:auto;background:var(--the);border:1px solid var(--ke);border-radius:10px}
table{border-collapse:collapse;width:100%;min-width:560px}th,td{padding:8px 10px;border-bottom:1px solid var(--ke);text-align:right;white-space:nowrap}
th{font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:var(--mo);font-weight:600}
tr.tong td{font-weight:700;border-bottom:0}
td.am{color:var(--lo)}td.duong{color:var(--lai)}ul{margin:6px 0 0;padding-left:18px}li{margin:2px 0}
"""


def _bang(cot: list[str], dong: list[list[str]], tong: list[str] | None = None, trai: int | tuple = 0) -> str:
    """trai = cột (hoặc tuple các cột) canh trái (tên); các cột số canh phải."""
    trai = trai if isinstance(trai, tuple) else (trai,)
    st = lambda i: " style='text-align:left;white-space:normal;min-width:150px'" if i in trai else ""  # noqa: E731
    h = "".join(f"<th{st(i)}>{c}</th>" for i, c in enumerate(cot))
    b = "".join("<tr>" + "".join(f"<td{st(i)}>{c}</td>" for i, c in enumerate(d)) + "</tr>" for d in dong)
    t = ("<tr class='tong'>" + "".join(f"<td{st(i)}>{c}</td>" for i, c in enumerate(tong)) + "</tr>") if tong else ""
    return f"<div class='bang'><table><thead><tr>{h}</tr></thead><tbody>{b}{t}</tbody></table></div>"


def _lai(x: float) -> str:
    return f"<span class='{'duong' if x >= 0 else 'am'}'>{vnd(x)}</span>"


def _bang_hang_muc(hm: dict | None) -> str:
    """Doanh thu sàn theo hạng mục (chủ trang thêm 10/10/2026) — hm = bao_cao_ads_telegram.hang_muc_san(tu, den)."""
    if not hm:
        return ""
    import hang_muc_san
    dong = []
    for san, hang, t in hang_muc_san.dong(hm):
        dong += [[e(san) if i == 0 else "", e(ten), vnd(v), _pt(v, t)] for i, (ten, v, _) in enumerate(hang)]
        dong.append([f"<b>{e(san)}</b>", "<b>Tổng</b>", f"<b>{vnd(t)}</b>", "100%"])
    return ("<h2>Doanh thu sàn theo hạng mục</h2>" + _bang(["Sàn", "Hạng mục", "Doanh thu", "Tỷ trọng"], dong, trai=(0, 1))
            + "<p class='mo'>Số trên trang người bán (Shopee: Phân tích bán hàng → Nguồn doanh thu, đơn đã xác nhận; "
              "TikTok: Compass → Tổng quan, GMV) — gồm cả đơn sau này huỷ/hoàn nên lệch với doanh thu Nhanh ở trên; "
              f"dùng để xem tỷ trọng. Cập nhật {e(hm['luc'])}" + (" — " + e("; ".join(hm["thieu"])) if hm["thieu"] else "")
            + ".</p>")


def tao_html(nhan: str, rows: list[dict], nh: dict, cp_san: dict | None, top: dict | None = None,
             hm: dict | None = None) -> str:
    t = tinh(rows, nh, cp_san)
    T = t["tong"]
    kpi = "".join(f"<div class='the {c}'><div class='mo'>{ten}</div><div class='so'>{vnd(v)}</div>"
                  f"<div class='mo'>{phu}</div></div>"
                  for ten, v, c, phu in [
                      ("Doanh thu", T["dt"], "", "4 kênh"),
                      ("Giá vốn", T["gv"], "", f"{_pt(T['gv'], T['dt'])} doanh thu"),
                      ("Phí sàn", T["phi"], "", f"{_pt(T['phi'], T['dt'])} doanh thu"),
                      ("CP quảng cáo (FB + sàn)", T["qc"], "", f"{_pt(T['qc'], T['dt'])} doanh thu"),
                      ("Lãi sau GV, phí sàn, QC", T["lai"], "lai", f"{_pt(T['lai'], T['dt'])} doanh thu")])
    # % phí sàn, % CP QC trên doanh thu từng kênh (chủ trang thêm 06/10/2026)
    kenh = _bang(["Kênh", "Doanh thu", "Giá vốn", "% GV", "Phí sàn", "% phí sàn", "CP QC", "% CP QC", "Lãi", "% lãi"],
                 [[e(k["ten"]) + (f" <span class='mo'>({k['ghi_qc']})</span>" if k["ghi_qc"] else ""), vnd(k["dt"]),
                   vnd(k["gv"]), _pt(k["gv"], k["dt"]),
                   vnd(k["phi"]) if k["phi"] else "—", _pt(k["phi"], k["dt"]) if k["phi"] else "—",
                   vnd(k["qc"]) if k["qc"] else "—", _pt(k["qc"], k["dt"]) if k["qc"] else "—",
                   _lai(k["lai"]), _pt(k["lai"], k["dt"])] for k in t["kenh"]],
                 ["Tổng", vnd(T["dt"]), vnd(T["gv"]), _pt(T["gv"], T["dt"]), vnd(T["phi"]), _pt(T["phi"], T["dt"]),
                  vnd(T["qc"]), _pt(T["qc"], T["dt"]), _lai(T["lai"]), _pt(T["lai"], T["dt"])])
    nv = nh["nv"]
    nv_b = _bang(["Nhân viên (người tạo đơn)", "Đơn", "Doanh thu", "Giá vốn", "% GV"],
                 [[e(a["ten"]), _so(a["don"]), vnd(a["dt"]), vnd(a.get("gv", 0)), _pt(a.get("gv", 0), a["dt"])] for a in nv],
                 ["Tổng", _so(sum(a["don"] for a in nv)), vnd(t["kenh"][0]["dt"]), vnd(t["kenh"][0]["gv"]),
                  _pt(t["kenh"][0]["gv"], t["kenh"][0]["dt"])])
    bl = nh["ban_le"]
    bl_b = _bang(["Cửa hàng", "Hoá đơn", "Khách trả", "Doanh thu", "Giá vốn", "% GV"],
                 [[e(a["ten"]), _so(a["don"]), _so(a.get("tra", 0)), vnd(a["dt"]), vnd(a.get("gv", 0)), _pt(a.get("gv", 0), a["dt"])]
                  for a in bl]) if bl else "<p class='mo'>Không có hoá đơn.</p>"
    san = nh["san"]
    san_b = _bang(["Sàn", "Đơn", "Doanh thu", "Giá vốn", "Phí sàn", "trong đó ước tính", "CP QC", "% QC"],
                  [[e(k["kenh"]), _so(k["don"]), vnd(k["dt"]), vnd(k.get("gv", 0)), vnd(k.get("phi", 0)),
                    (f"{k.get('don_uoc', 0)} đơn × {k.get('ty_le_phi', 0):.1%}".replace(".", ",") if k.get("don_uoc") else "—"),
                    vnd((cp_san or {}).get(k["kenh"]) or 0), _pt((cp_san or {}).get(k["kenh"]) or 0, k["dt"])] for k in san]) \
        if san else "<p class='mo'>Không có đơn sàn.</p>"
    tk: dict[str, list[float]] = {}
    for r in t["rows"]:
        a = tk.setdefault(r["tk"], [0, 0, 0])
        a[0] += r["chi"]; a[1] += r["tc"]; a[2] += r["mua"]
    fb_b = _bang(["Tài khoản QC", "Chi tiêu", "Trò chuyện", "Giá/TC", "Lượt mua", "Giá/mua"],
                 [[e(k), vnd(c), _so(n), vnd(c / n) if n else "—", _so(m), vnd(c / m) if m else "—"]
                  for k, (c, n, m) in sorted(tk.items(), key=lambda x: -x[1][0])],
                 ["Tổng", vnd(t["chi_fb"]), _so(sum(v[1] for v in tk.values())), "", _so(sum(v[2] for v in tk.values())), ""])
    top_b = ""
    if top:
        c = top["kenh"][0]   # bảng "Tổng các kênh" của top_sp_nhan_vien.du_lieu
        top_b = "<h2>Top 10 sản phẩm cha — tổng các kênh</h2>" + _bang(
            ["#", "Sản phẩm", "SL", "Doanh thu", "Tồn kho tổng"],
            [[str(i), e(r["ten"]) + (f" <span class='mo'>gộp {e(', '.join(r['gom']))}</span>" if r["gom"] else "")
              + (" <span class='mo'>(combo)</span>" if r["combo"] else ""), _so(r["sl"]), vnd(r["dt"]),
              _so(r["ton"]) if r["ton"] is not None else "—"] for i, r in enumerate(c["dong"], 1)], trai=1)
    ghi = ["Lãi = doanh thu − giá vốn − phí sàn − CP quảng cáo (Ads FB + Shopee Ads + TikTok GMV Max); "
           "<b>chưa trừ</b> ship, lương, mặt bằng, vận hành.",
           "Nhân viên online: đơn theo người tạo đơn, bỏ huỷ; doanh thu = Tổng thu + chuyển khoản; giá vốn = giá vốn "
           "bình quân ghi trong đơn (đơn hoàn không tính).",
           "Cửa hàng: hoá đơn bán lẻ, bán − khách trả; giá vốn theo giá vốn bình quân hiện tại của mã.",
           "Sàn: đơn tạo trong kỳ − huỷ − hoàn (trừ cả hàng trả sau giao); phí sàn = tiền hàng − tiền sàn trả shop; "
           "đơn chưa quyết toán ước tính theo tỉ lệ phí thật (Shopee: đơn đã quyết toán; TikTok: phí / doanh thu sao kê "
           "TikTok 30 ngày — Nhanh không còn ghi tiền TikTok quyết toán thật từ ~26/09/2026)."]
    if cp_san:
        ghi.append(f"CP QC sàn lấy từ trang người bán, cập nhật {e(cp_san['luc'])}"
                   + (" — " + e("; ".join(cp_san["thieu"])) if cp_san["thieu"] else "") + ".")
    luc = datetime.now(VN_TZ).strftime("%H:%M %d/%m/%Y")
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>BÁO CÁO {e(TEN_DN)} — {e(nhan)}</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>BÁO CÁO {e(TEN_DN)}</h1><div class="mo">{e(nhan)} · tạo lúc {luc}</div>
<div class="kpi">{kpi}</div>
<h2>Theo kênh</h2>{kenh}
<h2>Nhân viên online</h2>{nv_b}
<h2>Cửa hàng bán lẻ</h2>{bl_b}
<h2>Sàn Shopee · TikTok Shop</h2>{san_b}
{_bang_hang_muc(hm)}
<h2>Ads Facebook</h2>{fb_b}
{top_b}
<h2>Cách tính</h2><div class="the"><ul>{''.join(f'<li>{g}</li>' for g in ghi)}</ul></div>
</div></body></html>"""
