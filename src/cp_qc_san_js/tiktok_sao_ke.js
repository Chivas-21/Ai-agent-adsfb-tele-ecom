/*
 * Sao kê TikTok Shop theo ngày (doanh thu / phí / điều chỉnh) — chạy trong seller-vn.tiktok.com/finance/bills?tab=statements
 * đã đăng nhập (Claude in Chrome), sau khi danh sách "Báo cáo" tải xong (có sẵn request statement/list/detail làm URL
 * gốc — mở trang rồi chạy ngay performance.setResourceTimingBufferSize(5000)). Gọi:
 *   window.__skTikTokChay('2026-10-01'); kết quả ở window.__skTikTokKQ = {xong, ngay: {d: {dt, phi, dc}}, loi}.
 * Phân trang theo from/size (pagination_type 1). Ngày = ngày báo cáo (bill_period, giờ VN); nhiều sao kê cùng ngày thì
 * cộng. Phí trả về số dương. Xem src/phi_san_tiktok.py.
 */
window.__skTikTokChay = async function (tu) {
  const kq = window.__skTikTokKQ = { xong: false, ngay: {}, loi: '', trang: 0 };
  try {
    const goc = performance.getEntriesByType('resource').map(x => x.name).find(n => n.includes('/pay/statement/list/detail'));
    if (!goc) throw new Error('no statement/list/detail');
    const so = a => Number((a || {}).amount || 0);
    const u = new URL(goc, location.origin), SIZE = 50;
    u.searchParams.set('size', String(SIZE));
    for (let from = 0; kq.trang < 30; from += SIZE) {
      u.searchParams.set('from', String(from));
      const j = await fetch(u, { credentials: 'include' }).then(r => r.json());
      if (j.code !== 0) throw new Error('statement/list/detail: ' + (j.message || j.code));
      const ds = j.data.statement_records || [];
      let cu = false;
      for (const r of ds) {
        const d = new Date(Number(r.bill_period) + 7 * 3600e3).toISOString().slice(0, 10);
        if (d < tu) { cu = true; continue; }
        const o = kq.ngay[d] = kq.ngay[d] || { dt: 0, phi: 0, dc: 0 };
        o.dt += so(r.earning_amount); o.phi += Math.abs(so(r.fee_amount)); o.dc += so(r.adjust_amount);
      }
      kq.trang++;
      if (cu || ds.length < SIZE) break;
      await new Promise(res => setTimeout(res, 500));
    }
  } catch (e) { kq.loi = String(e && e.message || e); }
  kq.xong = true;
  return kq;
};
