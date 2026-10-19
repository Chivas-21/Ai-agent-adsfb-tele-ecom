"""Nhân (nhân bản) nhóm quảng cáo — dùng cho lệnh Telegram /nhanban sau báo cáo đề xuất nhân nhóm.

Bản sao nằm cùng chiến dịch với nhóm gốc, cùng đối tượng / tối ưu / vị trí, gắn lại đúng các mẫu quảng cáo (creative)
của nhóm gốc. Nhóm mới để TẮT (chủ trang tự bật trên Ads Manager), quảng cáo bên trong bật sẵn — bật nhóm là chạy.
Tên: "<tên gốc> - Nhân dd/mm" (ngày nhân).

Không dùng API /{adset}/copies: nhóm cũ báo lỗi 1870197 (trường targeting_optimization đã bị gỡ) — tự đọc cấu
hình rồi tạo lại, bỏ targeting_optimization và attribution_spec (giá trị cũ bị từ chối, lỗi 1885501/1885423).
"""
import json
from datetime import datetime
from pathlib import Path

import fb_ads_create as fb

TRUONG = ("name,account_id,campaign_id,optimization_goal,billing_event,bid_strategy,bid_amount,promoted_object,"
          "destination_type,targeting,daily_budget,lifetime_budget,end_time,is_dynamic_creative,pacing_type")
TOI_DA_NGAN_SACH = 500_000   # đ/ngày mỗi nhóm nhân — như ngưỡng hàng đợi lên camp
TOI_DA_SO_NHOM = 10          # nhóm gốc mỗi lần
TOI_DA_BAN_SAO = 5           # bản sao mỗi nhóm gốc ("nhân thành 5 nhóm")
TOI_DA_TONG_BAN = 20         # tổng số nhóm mới mỗi lần
# Sổ nhân trong ngày {ngày: {nhóm gốc: [nhóm mới]}} — báo cáo đề xuất ghi "đã nhân camp" cho nhóm có trong sổ hôm nay
SO_NHAN = Path(__file__).resolve().parent.parent / "data" / "nhan_nhom_so.json"


def _doc_so() -> dict:
    try:
        return json.loads(SO_NHAN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def da_nhan_hom_nay() -> set[str]:
    return set(_doc_so().get(f"{datetime.now():%Y-%m-%d}", {}))


def _ghi_so(goc: str, moi: str) -> None:
    so = _doc_so()
    ngay = f"{datetime.now():%Y-%m-%d}"
    so.setdefault(ngay, {}).setdefault(goc, []).append(moi)
    so = dict(sorted(so.items())[-14:])  # giữ 14 ngày gần nhất
    SO_NHAN.write_text(json.dumps(so, ensure_ascii=False), encoding="utf-8")


def doc_nhom(adset_id: str) -> dict:
    """Cấu hình nhóm gốc + ngân sách hiện tại (None = ngân sách theo chiến dịch / CBO)."""
    a = fb._goi("GET", adset_id, {"fields": TRUONG})
    a["ngan_sach"] = int(a["daily_budget"]) if a.get("daily_budget") not in (None, "", "0") else None
    return a


def nhan(adset_id: str, ngan_sach: int | None = None, thu_tu: int | None = None) -> dict:
    """Tạo bản sao TẮT của 1 nhóm. ngan_sach None = giữ như nhóm gốc; thu_tu = số bản khi nhân nhiều bản ("(2)").
    Trả về {"id","ten","acc","so_qc","loi_qc"}."""
    a = doc_nhom(adset_id)
    acc = a["account_id"]
    t = a["targeting"]
    t.pop("targeting_optimization", None)
    # Nhóm cũ không có targeting_automation → Facebook giờ bắt khai báo (lỗi 1870227); giữ đúng như gốc = Advantage+ tắt
    t.setdefault("targeting_automation", {"advantage_audience": 0})
    ten =f"{a['name']} - Nhân {datetime.now():%d/%m}" + (f" ({thu_tu})" if thu_tu else "")
    data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in a.items()
            if k not in ("id", "account_id", "name", "targeting", "lifetime_budget", "daily_budget", "ngan_sach")
            and v not in (None, "", "0")}
    data.update({"name": ten, "targeting": json.dumps(t), "status": "PAUSED"})
    if a["ngan_sach"] is not None:  # nhóm CBO: ngân sách nằm ở chiến dịch, không đặt riêng
        data["daily_budget"] = int(ngan_sach or a["ngan_sach"])
    moi = fb._goi("POST", f"act_{acc}/adsets", data)["id"]
    _ghi_so(adset_id, moi)

    so_qc, loi_qc = 0, []
    ads = fb._goi("GET", f"{adset_id}/ads", {"fields": "name,status,creative{id}", "limit": 20}).get("data", [])
    for ad in ads:
        if ad.get("status") in ("DELETED", "ARCHIVED") or not (ad.get("creative") or {}).get("id"):
            continue
        try:
            fb._goi("POST", f"act_{acc}/ads", {"name": ad["name"], "adset_id": moi, "status": "ACTIVE",
                                               "creative": json.dumps({"creative_id": ad["creative"]["id"]})})
            so_qc += 1
        except RuntimeError as e:
            loi_qc.append(fb.an_bi_mat(e)[:150])
    return {"id": moi, "ten": ten, "acc": acc, "so_qc": so_qc, "loi_qc": loi_qc}


def link_nhom(acc: str, adset_id: str) -> str:
    return f"https://adsmanager.facebook.com/adsmanager/manage/adsets?act={acc}&selected_adset_ids={adset_id}"
