/*
 * Doanh thu TikTok Shop theo hạng mục (LIVE / Video / Thẻ sản phẩm = TTMS) theo ngày — chạy trong bất kỳ trang nào của
 * seller-vn.tiktok.com đã đăng nhập (Claude in Chrome), cùng lượt với src/cp_qc_san_js/tiktok.js.
 * Gọi: window.__hmTikTokChay(['2026-10-01', ...]); kết quả ở window.__hmTikTokKQ = {xong, ngay: {d: {tong, live, video,
 * the}}, loi}. Nguồn: Compass → Tổng quan (insights unified/query us_overview_stats): metric 4024 GMV, 4029 LIVE,
 * 4037 Video, 4033 Thẻ sản phẩm. where_filter.ready_time bắt buộc có (giá trị không ảnh hưởng số). Xem src/hang_muc_san.py.
 */
window.__hmTikTokChay = async function (days) {
  const kq = window.__hmTikTokKQ = { xong: false, ngay: {}, loi: '', da: 0, tong_ngay: days.length };
  try {
    const csrf = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || '';
    const url = '/api/v2/insights/seller/unified/query/us_overview_stats?locale=vi-VN&language=vi&aid=4068&app_name=i18n_ecom_shop&shop_region=VN';
    const M = { tong: 4024, live: 4029, video: 4037, the: 4033 };
    for (const d of days) {
      const b = { query_condition: [{ query_time: { start: d, end: d, timezone_offset: 25200 },
        date_completion: { enabled: true, granularity: 0 }, where_filter: { ready_time: { value_list: [d] } }, group_by: [],
        metrics: Object.values(M).map(id => ({ metric_id: id, metric_type: id === 4024 ? 201 : 1 })) }] };
      let v;
      for (let lan = 1; lan <= 3; lan++) {
        const t = await fetch(url, { method: 'POST', credentials: 'include', headers: { 'content-type': 'application/json', 'x-csrftoken': csrf },
          body: JSON.stringify(b) }).then(r => r.text()).catch(e => String(e));
        try { v = JSON.parse(t).data[0].intervals[0].rows[0].values; break; } catch (e) {
          if (lan === 3) throw new Error('us_overview_stats ' + d + ': ' + t.slice(0, 150));
          await new Promise(res => setTimeout(res, 1500 * lan));
        }
      }
      kq.ngay[d] = Object.fromEntries(Object.entries(M).map(([k, id]) => [k, Number(v[id] ? JSON.parse(v[id]).value : 0) || 0]));
      kq.da++;
      await new Promise(res => setTimeout(res, 300));
    }
  } catch (e) { kq.loi = String(e && e.message || e); }
  kq.xong = true;
  return kq;
};
