/*
 * Doanh thu Shopee theo hạng mục (Thẻ sản phẩm / Live / Video / Affiliate) theo ngày của SHOP ĐANG MỞ — chạy trong
 * banhang.shopee.vn đã đăng nhập (Claude in Chrome), cùng lượt với src/cp_qc_san_js/shopee.js.
 * Gọi: window.__hmShopeeChay(['2026-10-01', ...]); kết quả ở window.__hmShopeeKQ = {xong, ten, ngay: {d: {tong, the,
 * live, video, aff}}, loi}. Nguồn: Phân tích bán hàng → Nguồn doanh thu (mydata dashboard/traffic-sources, đơn đã
 * xác nhận); ngày đã qua period=day, hôm nay period=real_time. 4 hạng mục cộng lại = tổng. Xem src/hang_muc_san.py.
 */
window.__hmShopeeChay = async function (days) {
  const kq = window.__hmShopeeKQ = { xong: false, ten: '', ngay: {}, loi: '', da: 0, tong_ngay: days.length };
  try {
    const shop = (await fetch('/api/selleraccount/shop_info/').then(r => r.json())).data || {};
    if (!shop.shop_id) throw new Error('Không đọc được shop đang mở — đăng nhập lại Shopee.');
    kq.ten = shop.name;
    const VN = 7 * 3600, nay = new Date(Date.now() + VN * 1000).toISOString().slice(0, 10);
    for (const d of days) {
      const S = Date.parse(d + 'T00:00:00Z') / 1000 - VN;
      const q = new URLSearchParams({ start_time: S, end_time: S + 86400, period: d === nay ? 'real_time' : 'day',
        order_type: 'confirmed', need_paid_ads_data: 'false' });
      let j;
      for (let lan = 1; lan <= 3; lan++) {
        j = await fetch('/api/mydata/v1/dashboard/traffic-sources/?' + q).then(r => r.json()).catch(e => ({ code: -1, msg: String(e) }));
        if (j.code === 0 && j.result) break;
        if (lan === 3) throw new Error('traffic-sources ' + d + ': ' + (j.msg || j.message || j.code));
        await new Promise(res => setTimeout(res, 1500 * lan));
      }
      const o = j.result.overview || {};
      kq.ngay[d] = { tong: o.total_sales || 0, the: o.product_card || 0, live: o.live || 0, video: o.video || 0, aff: o.affiliate || 0 };
      kq.da++;
      await new Promise(res => setTimeout(res, 300));
    }
  } catch (e) { kq.loi = String(e && e.message || e); }
  kq.xong = true;
  return kq;
};
