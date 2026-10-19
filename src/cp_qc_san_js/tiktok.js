/*
 * Chi phí quảng cáo TikTok Shop (GMV Max) theo ngày — chạy trong seller-vn.tiktok.com/ads-creation/dashboard đã đăng nhập
 * (trang phải tải xong để có sẵn request post_campaign_list làm URL gốc). Claude in Chrome gọi:
 *   window.__cpqcTikTokChay(['2026-10-01', ...]); kết quả ở window.__cpqcTikTokKQ = {xong, ngay: {d: {product, live}}, loi}.
 * Product GMV Max = external_type 304/307 + gmv_roi_mode 2; LIVE GMV Max = 305. Xem src/cp_qc_san.py.
 */
window.__cpqcTikTokChay = async function (days) {
  const kq = window.__cpqcTikTokKQ = { xong: false, ngay: {}, loi: '', da: 0, tong_ngay: days.length };
  try {
    const url = performance.getEntriesByType('resource').map(x => x.name).find(n => n.includes('oec/stat/post_campaign_list'));
    if (!url) throw new Error('Chưa thấy request post_campaign_list — mở trang Quảng cáo cửa hàng (GMV Max) và chờ tải xong.');
    const csrf = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || '';
    const cp = async (d, loai, roi) => {
      let trang = 1, c = 0, n = 0;
      while (true) {
        const b = { query_list: ['cost'], start_time: d, end_time: d, order_field: 'cost', order_type: 1, page: trang, page_size: 100,
          campaign_shop_automation_type: 2, external_type_list: loai,
          filters: roi ? [{ field: 'gmv_roi_mode', in_field_values: ['2'], filter_type: 10 }] : [] };
        let r;
        for (let lan = 1; lan <= 3; lan++) {
          r = await fetch(url, { method: 'POST', credentials: 'include', headers: { 'content-type': 'application/json', 'x-csrftoken': csrf }, body: JSON.stringify(b) })
            .then(x => x.json()).catch(e => ({ code: -1, msg: String(e) }));
          if (r.code === 0) break;
          if (lan === 3) throw new Error('post_campaign_list ' + d + ': ' + (r.msg || r.code));
          await new Promise(res => setTimeout(res, 1500 * lan));
        }
        const ds = r.data.table || [];
        for (const x of ds) c += Number((x.metrics || x).cost || 0);
        n += ds.length;
        const tong = (r.data.pagination || {}).total_count || 0;
        if (!ds.length || n >= tong || trang > 20) break;
        trang++;
      }
      return c;
    };
    for (const d of days) {
      kq.ngay[d] = { product: await cp(d, ['304', '307'], true), live: await cp(d, ['305'], false) };
      kq.da++;
    }
  } catch (e) { kq.loi = String(e && e.message || e); }
  kq.xong = true;
  return kq;
};
