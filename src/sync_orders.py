"""
Đồng bộ đơn hàng Nhanh v3 về SQLite, sau đó cập nhật tỷ lệ phí sàn theo kênh và danh sách mẫu quà tặng kèm.

    python src/sync_orders.py --days 70          # nạp lịch sử theo ngày tạo đơn (lần đầu)
    python src/sync_orders.py --updated          # hằng ngày: chỉ lấy đơn có thay đổi từ lần sync trước
                                                 # (bắt được đơn chuyển sang giao thành công / hoàn / hủy)
"""
import argparse
import datetime as dt

from constants import ORDER_STATUS, STATUS_GROUP, commercial_channel
from db import get_conn, get_state, init_db, refresh_derived_tables, set_state
from nhanh_client import VN_TZ, NhanhClient


def ts_to_text(ts):
    if not ts:
        return None
    return dt.datetime.fromtimestamp(int(ts), tz=VN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def upsert_order(conn, order: dict):
    info = order.get("info") or {}
    channel = order.get("channel") or {}
    carrier = order.get("carrier") or {}
    order_id = info.get("id")
    status_id = info.get("status")
    conn.execute(
        """INSERT INTO orders (order_id, created_at, updated_at, order_type, status_id, status_name, status_group,
               sale_channel_id, channel, traffic_source, shop_name, depot_id, carrier_name, delivered_at, ship_fee, ecom_fee)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(order_id) DO UPDATE SET
               updated_at=excluded.updated_at, order_type=excluded.order_type, status_id=excluded.status_id,
               status_name=excluded.status_name, status_group=excluded.status_group,
               sale_channel_id=excluded.sale_channel_id, channel=excluded.channel,
               traffic_source=excluded.traffic_source, shop_name=excluded.shop_name, depot_id=excluded.depot_id,
               carrier_name=excluded.carrier_name, delivered_at=excluded.delivered_at,
               ship_fee=excluded.ship_fee, ecom_fee=excluded.ecom_fee""",
        (
            order_id,
            ts_to_text(info.get("createdAt")),
            ts_to_text(info.get("updatedAt")),
            info.get("type"),
            status_id,
            ORDER_STATUS.get(status_id, str(status_id)),
            STATUS_GROUP.get(status_id, "other"),
            channel.get("saleChannel"),
            commercial_channel(channel.get("saleChannel"), channel.get("trafficSource")),
            channel.get("trafficSource"),
            channel.get("shopName"),
            info.get("depotId"),
            carrier.get("name"),
            ts_to_text(carrier.get("deliveryAt")),
            num(carrier.get("shipFee")),
            num(carrier.get("ecomFee")),
        ),
    )
    conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
    for line_no, p in enumerate(order.get("products") or []):
        conn.execute(
            """INSERT INTO order_items (order_id, line_no, product_id, sku, name, quantity,
                   price_after_vat, discount_amount, total_amount, avg_cost)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order_id, line_no, p.get("productId"), p.get("code"), p.get("name"),
                num(p.get("quantity")), num(p.get("priceAfterVAT")), num(p.get("discountAmount")),
                num(p.get("totalAmount")), num(p.get("avgCost")),
            ),
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, help="Nạp đơn tạo trong N ngày gần nhất")
    parser.add_argument("--updated", action="store_true", help="Chỉ lấy đơn thay đổi từ lần sync trước")
    args = parser.parse_args()

    init_db()
    conn = get_conn()
    client = NhanhClient()
    now = dt.datetime.now(tz=VN_TZ)

    if args.updated:
        last = get_state(conn, "orders_updated_at")
        start = dt.datetime.fromisoformat(last) - dt.timedelta(hours=1) if last else now - dt.timedelta(days=3)
        start = max(start, now - dt.timedelta(days=30))
        orders = client.list_orders(start, now, by="updatedAt")
    else:
        start = now - dt.timedelta(days=args.days or 70)
        orders = client.list_orders(start, now, by="createdAt")

    count = 0
    for order in orders:
        upsert_order(conn, order)
        count += 1
        if count % 500 == 0:
            conn.commit()
            print(f"  ... {count} đơn")
    set_state(conn, "orders_updated_at", now.isoformat())
    refresh_derived_tables(conn)
    conn.commit()

    summary = conn.execute(
        """SELECT channel, status_group, COUNT(*) n FROM orders
           WHERE created_at >= ? GROUP BY channel, status_group ORDER BY channel, status_group""",
        (start.strftime("%Y-%m-%d %H:%M:%S"),),
    ).fetchall()
    rates = conn.execute("SELECT channel, ecom_fee_rate FROM channel_fee_rates WHERE ecom_fee_rate > 0").fetchall()
    conn.close()

    print(f"Đã đồng bộ {count} đơn (từ {start:%d/%m/%Y %H:%M}).")
    for r in summary:
        print(f"  {r['channel']:<12} {r['status_group']:<10} {r['n']:>6}")
    print("Tỷ lệ phí sàn 8 tuần: " + " · ".join(f"{r['channel']} {r['ecom_fee_rate']:.1%}" for r in rates))


if __name__ == "__main__":
    main()
