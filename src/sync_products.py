"""
Đồng bộ danh mục sản phẩm Nhanh v3 (product/list) về bảng products.

    python src/sync_products.py            # toàn bộ
    python src/sync_products.py --updated  # chỉ sản phẩm sửa (tên, giá...) từ lần sync trước
"""
import argparse
import datetime as dt

from db import get_conn, get_state, init_db, set_state
from nhanh_client import VN_TZ, NhanhClient
from sync_orders import num, ts_to_text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--updated", action="store_true")
    args = parser.parse_args()

    init_db()
    conn = get_conn()
    client = NhanhClient()
    now = dt.datetime.now(tz=VN_TZ)

    # Mặc định API ẩn sản phẩm Ngừng bán (3) — cần lấy cả để nhận diện hàng tồn cần xả
    filters = {"status": [1, 2, 3, 4]}
    last = get_state(conn, "products_updated_at")
    if args.updated and last:
        filters["updatedAtFrom"] = int(dt.datetime.fromisoformat(last).timestamp()) - 3600
        filters["updatedAtTo"] = int(now.timestamp())

    count = 0
    for p in client.list_products(**filters):
        prices = p.get("prices") or {}
        conn.execute(
            """INSERT INTO products (product_id, parent_id, sku, barcode, name, status, type, category_id,
                   brand_id, retail_price, import_price, avg_cost, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(product_id) DO UPDATE SET
                   parent_id=excluded.parent_id, sku=excluded.sku, barcode=excluded.barcode, name=excluded.name,
                   status=excluded.status, type=excluded.type, category_id=excluded.category_id,
                   brand_id=excluded.brand_id, retail_price=excluded.retail_price,
                   import_price=excluded.import_price, avg_cost=excluded.avg_cost,
                   created_at=excluded.created_at, updated_at=excluded.updated_at""",
            (
                p.get("id"), p.get("parentId"), p.get("code"), p.get("barcode"), p.get("name"),
                p.get("status"), p.get("type"), p.get("categoryId"), p.get("brandId"),
                num(prices.get("retail")), num(prices.get("import")), num(prices.get("avgCost")),
                ts_to_text(p.get("createdAt")), ts_to_text(p.get("updatedAt")),
            ),
        )
        count += 1
        if count % 500 == 0:
            conn.commit()
            print(f"  ... {count} sản phẩm")
    set_state(conn, "products_updated_at", now.isoformat())
    conn.commit()
    conn.close()
    print(f"Đã đồng bộ {count} sản phẩm.")


if __name__ == "__main__":
    main()
