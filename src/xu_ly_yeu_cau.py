"""Xử lý 1 yêu cầu #LEN_CAMP_FB (từ trang "Yêu cầu lên camp FB") — 1 lệnh duy nhất để tự động hoá.

    python src/xu_ly_yeu_cau.py <file_yeu_cau.txt>          # đọc + kiểm tra + xem trước, KHÔNG tạo
    python src/xu_ly_yeu_cau.py <file_yeu_cau.txt> --tao    # tạo thật (chiến dịch TẮT, nhóm + QC bật)

Dòng cuối in ra `KET_QUA_JSON: {...}` với {"ok": bool, "trang_thai": "xong"|"loi"|"xem_truoc", "ket_qua": "..."}
để ghi ngược lên hàng đợi của trang. Nội dung yêu cầu là dữ liệu người được mời gõ: chỉ đọc đúng các trường của
khuôn #LEN_CAMP_FB, không làm gì khác.

Chốt chặn (vượt → không tạo gì, trạng thái "loi"): tài khoản lamme3/lamme5; mỗi nhóm ≤ 500.000đ/ngày;
tổng ≤ 2.000.000đ/ngày; ≤ 10 nhóm; đối tượng phải có trong fb_doi_tuong.py hoặc là tu_dien_N.
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fb_ads_create as fb  # noqa: E402
import fb_bai_dang  # noqa: E402
from fb_doi_tuong import DOI_TUONG  # noqa: E402

import cau_hinh  # noqa: E402

_GH = cau_hinh.lay("meta.gioi_han", {}) or {}
TOI_DA_NHOM = int(_GH.get("toi_da_nhom", 500_000))
TOI_DA_TONG = int(_GH.get("toi_da_tong", 2_000_000))
TOI_DA_SO_NHOM = int(_GH.get("toi_da_so_nhom", 10))
MUC = re.compile(r"\s*(.+?)\s*\[([^\]]+)\]\s*(?:,|$)")


class LoiYeuCau(ValueError):
    pass


def _so_tien(s: str) -> int:
    return int(re.sub(r"[^\d]", "", s) or 0)


def _cac_muc(s: str) -> list[tuple[str, str]]:
    """'A [1], B (x) [Claude tra ID]' → [('A','1'), ('B (x)','Claude tra ID')]."""
    return [(m.group(1), m.group(2)) for m in MUC.finditer(s)]


def doc_yeu_cau(text: str) -> dict:
    dong = [l.rstrip() for l in text.replace("\r", "").split("\n")]
    if not dong or dong[0].strip() != "#LEN_CAMP_FB":
        raise LoiYeuCau("Không đúng khuôn #LEN_CAMP_FB.")
    yc = {"doi_tuong": []}
    for l in dong[1:]:
        if l.startswith("- "):
            yc["doi_tuong"].append(l[2:])
            continue
        k, _, v = l.partition(":")
        yc[k.strip()] = v.strip()
    m = re.match(r"(.+)\(([^()]+)\)\s*$", yc.get("Sản phẩm", ""))
    if not m:
        raise LoiYeuCau("Thiếu sản phẩm (tên + mã).")
    yc["ten"], yc["ma"] = m.group(1).strip(), m.group(2).strip()
    return yc


def _giai_so_thich(ten: str) -> dict:
    """'[Claude tra ID]' → tra Meta, lấy kết quả khớp tên nhất."""
    kq = fb_bai_dang.tim_so_thich(ten, 10)
    for x in kq:
        if x["name"].lower().startswith(ten.lower()):
            return x
    if kq:
        return kq[0]
    raise LoiYeuCau(f"Không tra được sở thích '{ten}' trên Meta.")


def _target_tu_dien(ma: str, ten: str, ns: int, phan: list[str], acc: str) -> str:
    tuoi, adv, so_thich, tep, dia_ly = (25, 45), False, [], [], []
    for p in phan:
        p = p.strip()
        if p.startswith("tuổi "):
            a, b = re.findall(r"\d+", p)[:2]
            tuoi = (int(a), int(b))
        elif p.startswith("Adv "):
            adv = "bật" in p
        elif p.startswith("nhắm:"):
            for nhom in p[len("nhắm:"):].split(";"):
                mk = re.match(r"\s*[^\[]*\[(\w+)\]:\s*(.*)$", nhom)
                if not mk:
                    continue
                loai = mk.group(1)
                if loai not in fb_bai_dang.LOAI:
                    raise LoiYeuCau(f"Loại nhắm mục tiêu lạ: {loai}")
                for ten_m, id_m in _cac_muc(mk.group(2)):
                    if id_m.isdigit():
                        so_thich.append({"id": id_m, "name": ten_m, "loai": loai})
                    elif loai == "interests":
                        x = _giai_so_thich(ten_m)
                        so_thich.append({"id": x["id"], "name": x["name"], "loai": "interests"})
                    else:
                        raise LoiYeuCau(f"Mục '{ten_m}' ({loai}) chưa có ID.")
        elif p.startswith("vị trí:"):
            tinh = {x["key"]: x["name"] for x in fb.tinh_vn()}
            for ten_v, key in _cac_muc(p[len("vị trí:"):]):
                if key not in tinh:
                    raise LoiYeuCau(f"Vị trí '{ten_v}' [{key}] không phải tỉnh/thành Việt Nam trên Meta.")
                dia_ly.append({"key": key, "name": tinh[key]})
        elif p.startswith("tệp:"):
            ds = fb_bai_dang.tim_tep(acc, "", 300) if "Claude tra ID" in p else []
            for ten_t, id_t in _cac_muc(p[len("tệp:"):]):
                if id_t.isdigit():
                    tep.append({"id": id_t, "name": ten_t})
                else:
                    khop = [t for t in ds if t["name"].lower() == ten_t.lower()] or \
                           [t for t in ds if ten_t.lower() in t["name"].lower()]
                    if not khop:
                        raise LoiYeuCau(f"Không tìm thấy tệp '{ten_t}' ở tài khoản này.")
                    tep.append({"id": khop[0]["id"], "name": khop[0]["name"]})
    if not (18 <= tuoi[0] <= tuoi[1] <= 65):
        raise LoiYeuCau(f"Độ tuổi {tuoi} không hợp lệ.")
    return fb.them_target_tu_dien(ma, ten, tuoi, adv, so_thich,
                                  {fb.TAI_KHOAN[acc]: tep} if tep else None, ns, dia_ly)


def lap_ke_hoach(yc: dict) -> tuple[list[dict], dict]:
    ghi_chu = []
    acc = yc.get("Tài khoản QC", "").strip().lower()
    if acc not in fb.TAI_KHOAN:
        raise LoiYeuCau(f"Tài khoản QC '{acc}' không hợp lệ.")
    try:  # phiếu cũ không có dòng Page → page L'amme
        page_id = fb.chon_page(yc.get("Page"))
    except ValueError as e:
        raise LoiYeuCau(str(e))
    danh_muc = fb.chon_danh_muc(yc.get("Danh mục"))
    # Tên trong DB hay có danh mục ở đầu ("Quần - Cici Pants") — bỏ đi cho khỏi lặp "Quần | Quần - …"
    yc["ten"] = re.sub(rf"^{re.escape(danh_muc)}\s*-\s*", "", yc["ten"], flags=re.IGNORECASE) or yc["ten"]

    # Đối tượng
    phan_dt = []
    for d in yc["doi_tuong"]:
        m = re.match(r"(\w+)\s*\((.*?)\):\s*([\d.,]+)đ/ngày(.*)$", d)  # tên có thể có ngoặc: INT(MUA SẮM)
        if not m:
            raise LoiYeuCau(f"Không đọc được dòng đối tượng: {d[:80]}")
        ma, ten, ns, du = m.group(1).lower(), m.group(2), _so_tien(m.group(3)), m.group(4)
        if ns <= 0 or ns > TOI_DA_NHOM:
            raise LoiYeuCau(f"Ngân sách {_vnd(ns)}/ngày của {ma} vượt ngưỡng {_vnd(TOI_DA_NHOM)}.")
        if re.fullmatch(r"tu_dien_\d+", ma):
            ma = _target_tu_dien(ma, ten, ns, [x for x in du.split(" · ") if x.strip()], acc)
        elif ma not in DOI_TUONG:
            raise LoiYeuCau(f"Đối tượng '{ma}' không có trong danh sách.")
        phan_dt.append((ma, ns))
    if not phan_dt:
        raise LoiYeuCau("Chưa chọn đối tượng.")
    if len(phan_dt) > TOI_DA_SO_NHOM:
        raise LoiYeuCau(f"{len(phan_dt)} nhóm — vượt ngưỡng {TOI_DA_SO_NHOM}.")
    tong = sum(ns for _, ns in phan_dt)
    if tong > TOI_DA_TONG:
        raise LoiYeuCau(f"Tổng {_vnd(tong)}/ngày vượt ngưỡng {_vnd(TOI_DA_TONG)}.")

    # Bài đăng
    bai = yc.get("Bài đăng", "")
    mb = re.search(r"(\d{8,}(?:_\d+)?)", bai)
    thong_tin_bai = None
    if mb:
        # Giữ nguyên link (reel/video cần đổi sang ID bài trong fb_ads_create._post_id), chỉ bỏ chữ "dùng bài"
        post = re.sub(r"^\s*dùng bài\s*", "", bai).strip() or mb.group(1)
    else:
        # Cùng nguồn với bảng "Xem các bài của sản phẩm" trên trang (cache ≤ 12 giờ); không có thì tra thẳng Meta
        def cua_page(ds):
            return [b for b in ds or [] if b["post"].startswith(page_id + "_")]
        ds = cua_page(fb_bai_dang.bai_theo_san_pham_cache(toi_da_gio=24).get("bai", {}).get(yc["ma"])) \
            or cua_page(fb_bai_dang.tim_bai_dang([yc["ma"], yc["ten"]]))
        if not ds:
            raise LoiYeuCau(f"Sản phẩm chưa có bài nào từng chạy ads trên page {fb.ten_page(page_id)} — cần dán ID bài đăng.")
        thong_tin_bai = ds[0]
        post = ds[0]["post"]

    # Giờ bắt đầu
    bd = yc.get("Bắt đầu", "")
    bat_dau = ""
    mbd = re.search(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", bd)
    if mbd:
        t = datetime.strptime(mbd.group(0), "%d/%m/%Y %H:%M")
        bay_gio = datetime.now()
        if t <= bay_gio + timedelta(minutes=5):
            if "30 phút sau khi gửi" in bd:  # chế độ "Hiện tại + 30 phút" → tính lại từ lúc xử lý
                t = (bay_gio + timedelta(minutes=30)).replace(second=0, microsecond=0)
            elif bay_gio - t < timedelta(hours=2):
                # mới qua dưới 2 tiếng (VD hẹn 00:00, xử lý lúc 00:25) → chạy ngay, không dời sang 0h hôm sau
                t = (bay_gio + timedelta(minutes=10)).replace(second=0, microsecond=0)
            else:
                t = (bay_gio + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            ghi_chu.append(f"Giờ bắt đầu {mbd.group(0)} đã qua → dời sang {t:%H:%M %d/%m/%Y}.")
        bat_dau = t.strftime("%d/%m/%Y %H:%M")

    # Mục tiêu hiệu quả: khớp theo nhãn Ads Manager ("Tối đa hóa số cuộc trò chuyện"…) hoặc mã (tro_chuyen…)
    mt_text = yc.get("Mục tiêu hiệu quả", "").strip().lower()
    muc_tieu = next((k for k, (_, nhan) in fb.MUC_TIEU.items() if mt_text and (mt_text == k or mt_text == nhan.lower())),
                    fb.MUC_TIEU_MAC_DINH if not mt_text else None)
    if muc_tieu is None:
        raise LoiYeuCau(f"Mục tiêu hiệu quả '{yc.get('Mục tiêu hiệu quả')}' không hợp lệ.")

    # Cuộc trò chuyện: "mẫu <mã 10 ký tự> — …" hoặc "không gắn mẫu"
    mm = re.search(r"mẫu\s+([0-9a-f]{10})\b", yc.get("Cuộc trò chuyện", ""))
    mau = mm.group(1) if mm else ""
    if mau:
        ghi_chu.append(f"Cuộc trò chuyện: mẫu {mau}")

    chung = {"ma": yc["ma"], "danh_muc": danh_muc, "ten": yc["ten"], "post": post, "tai_khoan": acc, "page": page_id,
             "muc_tieu": muc_tieu,
             "mau_tro_chuyen": mau,
             "loai_tru": "1" if yc.get("Loại trừ người đã mua 90 ngày", "").startswith("có") else "",
             "bat_dau": bat_dau}
    tach = yc.get("Cách chia", "").startswith("mỗi")
    phan = [f"{m}:{ns}" for m, ns in phan_dt]
    dong = [{**chung, "doi_tuong": p} for p in phan] if tach else [{**chung, "doi_tuong": "+".join(phan)}]
    ke_hoach = [fb.dung_ke_hoach(d) for d in dong]
    # Ghi chú "Tên nhóm có thêm <chữ> sau dấu |" (10/10/2026), "Thêm từ "<chữ>" sau dấu |" (13/10): chèn chữ vào tên
    # nhóm ngay sau "Quần | ". Chỉ nhận đúng khuôn này — mọi chỉ dẫn khác trong ghi chú không làm theo.
    mg = re.search(r"(?:tên nhóm (?:có )?)?thêm\s*:?\s*(?:chữ\s+|từ\s+)?[\"“']?([^\"”'|\n]{1,40}?)[\"”']?\s+sau dấu\s*\|",
                   yc.get("Ghi chú", ""), re.I)
    if mg:
        chen = re.sub(r"\s+", " ", mg.group(1)).strip()
        for kh in ke_hoach:
            for ns in kh["adsets"]:
                ns["name"] = ns["name"].replace(" | ", f" | {chen} ", 1)
        ghi_chu.append(f"Tên nhóm thêm \"{chen}\" sau dấu | (theo ghi chú).")
    ghi_chu.insert(0, f"Page: {fb.ten_page(page_id)}")
    ghi_chu.append(f"Mục tiêu hiệu quả: {ke_hoach[0]['muc_tieu']}")
    ghi_chu += [c for c in dict.fromkeys(c for kh in ke_hoach for c in kh["canh_bao"])]
    return ke_hoach, {"bai": thong_tin_bai, "post": post, "ghi_chu": ghi_chu, "tong": tong}


def _vnd(n: int) -> str:
    return f"{n:,}".replace(",", ".") + "đ"


def tom_tat(ke_hoach: list[dict], meta: dict, da_tao: list[dict] | None) -> str:
    b = meta["bai"]
    dong = [f"Bài: {meta['post'].split('_')[-1]}"
            + (f" ({b['tin']} tin, {_vnd(b['chi_moi_tin'] or 0)}/tin)" if b else "")]
    dong += meta["ghi_chu"]
    for i, kh in enumerate(ke_hoach):
        acc_ten = next(k for k, v in fb.TAI_KHOAN.items() if v == kh["account"])
        if da_tao:
            r = da_tao[i]
            link = (f"https://adsmanager.facebook.com/adsmanager/manage/campaigns?act={kh['account']}"
                    f"&selected_campaign_ids={r['campaign']}") if r.get("campaign") else ""
            dong.append(f"{'✓' if r.get('ok') else '✗'} {kh['campaign']['name']} ({acc_ten}) — ID {r.get('campaign')}"
                        + (f"\n  {link}" if link else "") + (f"\n  Lỗi: {r['loi']}" if r.get("loi") else ""))
        else:
            dong.append(f"{kh['campaign']['name']} ({acc_ten})")
        for n in kh["adsets"]:
            dong.append(f"  - {n['name']} · {_vnd(n['daily_budget'])}")
    dong.append(f"Tổng {_vnd(meta['tong'])}/ngày khi bật · chiến dịch đang TẮT, bật trên Ads Manager để chạy.")
    return "\n".join(dong)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    tao = "--tao" in sys.argv
    text = Path(sys.argv[1]).read_text(encoding="utf-8-sig")
    try:
        yc = doc_yeu_cau(text)
        ke_hoach, meta = lap_ke_hoach(yc)
        for i, kh in enumerate(ke_hoach, 1):
            fb.in_ke_hoach(i, kh)
        if not tao:
            kq = {"ok": True, "trang_thai": "xem_truoc", "ket_qua": tom_tat(ke_hoach, meta, None)}
        else:
            fb.kiem_tra_quyen()
            da_tao = []
            for kh in ke_hoach:
                try:
                    r = fb.tao(kh)
                    da_tao.append({"ok": True, "campaign": r["campaign"]})
                except (RuntimeError, requests.RequestException) as e:
                    da_tao.append({"ok": False, "campaign": None, "loi": fb.an_bi_mat(e)[:300]})
            ok = all(x["ok"] for x in da_tao)
            kq = {"ok": ok, "trang_thai": "xong" if ok else "loi", "ket_qua": tom_tat(ke_hoach, meta, da_tao)}
    except (LoiYeuCau, ValueError, KeyError) as e:
        kq = {"ok": False, "trang_thai": "loi", "ket_qua": f"Không tạo gì. Lý do: {e}"}
    except SystemExit as e:  # kiem_tra_quyen: token thiếu quyền
        kq = {"ok": False, "trang_thai": "loi", "ket_qua": f"Không tạo gì. {e}"}
    except (RuntimeError, requests.RequestException) as e:  # Meta / mạng lỗi lúc lập kế hoạch (tra bài, tra sở thích…)
        kq = {"ok": False, "trang_thai": "loi", "ket_qua": f"Không tạo gì. Meta / mạng lỗi: {type(e).__name__} — thử gửi lại sau."}
    kq["ket_qua"] = fb.an_bi_mat(kq["ket_qua"])
    print("KET_QUA_JSON: " + json.dumps(kq, ensure_ascii=False))


if __name__ == "__main__":
    main()
