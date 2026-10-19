/*
 * Chi phí quảng cáo Shopee theo ngày của SHOP ĐANG MỞ — chạy trong banhang.shopee.vn đã đăng nhập (Claude in Chrome).
 * Gọi: window.__cpqcShopeeChay(['2026-10-01', ...]); kết quả ở window.__cpqcShopeeKQ = {xong, ten, shop_id, ngay, loi}.
 * Tiền = số API trả / 1e5. Tổng/ngày = Σ cost chiến dịch homepage/query 4 loại + GMS (report/get). Xem src/cp_qc_san.py.
 */
window.__cpqcShopeeChay = async function (days) {
  const kq = window.__cpqcShopeeKQ = { xong: false, ten: '', shop_id: 0, ngay: {}, loi: '', da: 0, tong_ngay: days.length };
  try {
    const post = async (u, b) => {
      for (let lan = 1; lan <= 3; lan++) {
        const r = await fetch('/api/pas/v1/' + u, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(b) })
          .then(x => x.json()).catch(e => ({ code: -1, msg: String(e) }));
        if (r.code === 0) return r;
        if (lan === 3) throw new Error(u + ': ' + (r.msg || r.code));
        await new Promise(res => setTimeout(res, 1500 * lan));
      }
    };
    const tien = v => (Number(v) || 0) / 1e5;
    const shop = (await fetch('/api/selleraccount/shop_info/').then(r => r.json())).data || {};
    if (!shop.shop_id) throw new Error('Không đọc được shop đang mở — đăng nhập lại Shopee.');
    kq.ten = shop.name; kq.shop_id = shop.shop_id;
    const gmsId = ((await post('product/get_setup_status/', { reference_id: crypto.randomUUID() })).data || {}).gms?.campaign_id;
    const VN = 7 * 3600;
    for (const d of days) {
      const S = Date.parse(d + 'T00:00:00Z') / 1000 - VN, E = S + 86400 - 1;
      const o = { tong: 0 };
      for (const loai of ['product_homepage_v3', 'shop_homepage', 'live_stream_homepage', 'display']) {
        let off = 0, total = 0, c = 0;
        do {
          const b = { start_time: S, end_time: E, filter_list: [{ campaign_type: loai, state: 'all', search_term: '', is_valid_rebate_only: false }], offset: off, limit: 100 };
          if (loai === 'product_homepage_v3') b.use_paid_gmv = false;
          const r = await post('homepage/query/', b);
          total = r.data.total; for (const e of r.data.entry_list) c += tien(e.report?.cost); off += 100;
        } while (off < total);
        o[loai] = c; o.tong += c;
      }
      if (gmsId) {
        const t = await post('report/get/', { filter_params: { campaign_id: gmsId }, start_time: S, end_time: E, agg_type: 'product_gms', campaign_type: 'product_gms', need_ratio: false, use_paid_gmv: false });
        o.gms = tien(t.data?.[0]?.metrics?.cost); o.tong += o.gms;
      }
      kq.ngay[d] = o; kq.da++;
    }
  } catch (e) { kq.loi = String(e && e.message || e); }
  kq.xong = true;
  return kq;
};
