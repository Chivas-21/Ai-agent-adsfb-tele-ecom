"""Schema & tiện ích SQLite cho Commercial Engine."""
import sqlite3
from pathlib import Path

from constants import GIFT_HEAVY_SHARE, GIFT_MAX_UNIT_PRICE

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "commercial_engine.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    parent_id INTEGER,          -- -2: mã cha, -1: sản phẩm độc lập, >0: mã con
    sku TEXT,
    barcode TEXT,
    name TEXT,
    status INTEGER,
    type INTEGER,
    category_id INTEGER,
    brand_id INTEGER,
    retail_price REAL,
    import_price REAL,
    avg_cost REAL,
    created_at TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
CREATE INDEX IF NOT EXISTS idx_products_parent ON products(parent_id);

-- depot_id = 0 là tổng mọi kho
CREATE TABLE IF NOT EXISTS inventory_snapshots (
    snapshot_date TEXT,
    product_id INTEGER,
    depot_id INTEGER,
    remain REAL,
    available REAL,
    holding REAL,
    shipping REAL,
    transfering REAL,
    damaged REAL,
    PRIMARY KEY (snapshot_date, product_id, depot_id)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY,
    created_at TEXT,
    updated_at TEXT,
    order_type INTEGER,
    status_id INTEGER,
    status_name TEXT,
    status_group TEXT,
    sale_channel_id INTEGER,
    channel TEXT,
    traffic_source TEXT,
    shop_name TEXT,
    depot_id INTEGER,
    carrier_name TEXT,
    delivered_at TEXT,
    ship_fee REAL,
    ecom_fee REAL               -- tổng phí sàn; Nhanh chỉ ghi khi đã đối soát với sàn
);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);

CREATE TABLE IF NOT EXISTS order_items (
    order_id INTEGER,
    line_no INTEGER,
    product_id INTEGER,
    sku TEXT,
    name TEXT,
    quantity REAL,
    price_after_vat REAL,
    discount_amount REAL,
    total_amount REAL,
    avg_cost REAL,
    PRIMARY KEY (order_id, line_no)
);
CREATE INDEX IF NOT EXISTS idx_items_product ON order_items(product_id);

-- Tỷ lệ phí sàn / doanh thu theo kênh (đơn thành công 8 tuần), dùng ước tính phí cho đơn chưa đối soát
CREATE TABLE IF NOT EXISTS channel_fee_rates (
    channel TEXT PRIMARY KEY,
    ecom_fee_rate REAL,
    orders INTEGER,
    updated_at TEXT
);

-- Mẫu chủ yếu dùng làm quà tặng kèm (tỷ lệ chiếc tặng >= GIFT_HEAVY_SHARE)
CREATE TABLE IF NOT EXISTS gift_models (
    model_sku TEXT PRIMARY KEY,
    gift_share REAL,
    units REAL,
    updated_at TEXT
);

-- "Đề bài" Commercial Plan cho từng mẫu (model = mã cha) mỗi tuần
CREATE TABLE IF NOT EXISTS commercial_plans (
    week_start TEXT,
    model_sku TEXT,
    model_name TEXT,
    objective TEXT,        -- launch / scale / maintain / clearance
    target_units INTEGER,
    target_revenue REAL,
    target_profit REAL,    -- lợi nhuận sau phí sàn (doanh thu − giá vốn − phí sàn)
    lead_channel TEXT,
    price REAL,
    price_floor REAL,      -- sàn giá của kênh lead
    promo_guardrail TEXT,
    stock_available REAL,
    deadline TEXT,
    data_insight TEXT,     -- hệ thống tự điền từ số liệu
    insight TEXT,          -- Commercial điền
    usp TEXT,              -- Commercial điền
    status TEXT DEFAULT 'draft',
    PRIMARY KEY (week_start, model_sku)
);

CREATE TABLE IF NOT EXISTS channel_allocations (
    week_start TEXT,
    model_sku TEXT,
    channel TEXT,
    share REAL,
    target_units INTEGER,
    target_revenue REAL,
    PRIMARY KEY (week_start, model_sku, channel)
);

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Mỗi dòng sản phẩm trong đơn: mẫu (mã cha), tuần (thứ Hai), cờ hàng tặng, phí sàn phân bổ theo doanh thu dòng
-- (phí thực nếu đã đối soát, chưa có thì ước tính theo channel_fee_rates)
DROP VIEW IF EXISTS v_order_lines;
CREATE VIEW v_order_lines AS
SELECT x.*, x.gross_profit - x.ecom_fee AS contribution_profit
FROM (
    SELECT
        o.order_id, o.created_at,
        date(o.created_at, 'weekday 0', '-6 days') AS week_start,
        o.channel, o.shop_name, o.status_id, o.status_group, o.order_type, o.delivered_at,
        l.product_id, l.sku, l.name,
        COALESCE(pp.sku, p.sku, l.sku) AS model_sku,
        COALESCE(pp.name, p.name, l.name) AS model_name,
        l.quantity,
        CASE WHEN l.total_amount < __GIFT_MAX__ * l.quantity THEN 1 ELSE 0 END AS is_gift,
        l.total_amount AS revenue,
        l.avg_cost * l.quantity AS cogs,
        l.total_amount - l.avg_cost * l.quantity AS gross_profit,
        CASE WHEN o.ecom_fee > 0 AND l.order_amount > 0 THEN o.ecom_fee * l.total_amount / l.order_amount
             ELSE l.total_amount * COALESCE(r.ecom_fee_rate, 0) END AS ecom_fee,
        CASE WHEN o.ecom_fee > 0 THEN 1 ELSE 0 END AS fee_settled
    FROM (SELECT i.*, SUM(i.total_amount) OVER (PARTITION BY i.order_id) AS order_amount FROM order_items i) l
    JOIN orders o ON o.order_id = l.order_id
    LEFT JOIN products p ON p.product_id = l.product_id
    LEFT JOIN products pp ON pp.product_id = p.parent_id AND p.parent_id > 0
    LEFT JOIN channel_fee_rates r ON r.channel = o.channel
    WHERE o.order_type NOT IN (14, 15)
) x;

-- Dòng thuộc đơn hợp lệ (thành công + đang xử lý/giao), gồm cả hàng tặng: dùng cho doanh thu & lợi nhuận tổng
DROP VIEW IF EXISTS v_valid_lines;
CREATE VIEW v_valid_lines AS
SELECT * FROM v_order_lines WHERE status_group IN ('success', 'in_flight');

-- Doanh số theo mẫu: dòng hợp lệ, không phải hàng tặng, không thuộc mẫu quà tặng kèm
DROP VIEW IF EXISTS v_sales;
CREATE VIEW v_sales AS
SELECT * FROM v_valid_lines
WHERE is_gift = 0 AND model_sku NOT IN (SELECT model_sku FROM gift_models);

-- Tồn kho mới nhất (tổng mọi kho) theo mẫu
DROP VIEW IF EXISTS v_model_stock;
CREATE VIEW v_model_stock AS
SELECT
    COALESCE(pp.sku, p.sku) AS model_sku,
    SUM(s.available) AS available,
    SUM(s.remain) AS remain,
    SUM(s.shipping) AS shipping,
    SUM(s.holding) AS holding
FROM inventory_snapshots s
JOIN products p ON p.product_id = s.product_id
LEFT JOIN products pp ON pp.product_id = p.parent_id AND p.parent_id > 0
WHERE s.depot_id = 0
  AND s.snapshot_date = (SELECT MAX(snapshot_date) FROM inventory_snapshots)
GROUP BY COALESCE(pp.sku, p.sku);
""".replace("__GIFT_MAX__", str(GIFT_MAX_UNIT_PRICE))


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def refresh_derived_tables(conn, weeks: int = 8):
    """Cập nhật tỷ lệ phí sàn theo kênh và danh sách mẫu quà tặng kèm sau mỗi lần đồng bộ đơn."""
    conn.execute("DELETE FROM channel_fee_rates")
    conn.execute(
        """INSERT INTO channel_fee_rates (channel, ecom_fee_rate, orders, updated_at)
           SELECT o.channel, COALESCE(SUM(o.ecom_fee) / NULLIF(SUM(t.amount), 0), 0), COUNT(*),
                  datetime('now', 'localtime')
           FROM orders o
           JOIN (SELECT order_id, SUM(total_amount) AS amount FROM order_items GROUP BY order_id) t
             ON t.order_id = o.order_id
           WHERE o.status_group = 'success' AND o.created_at >= datetime('now', 'localtime', ?)
           GROUP BY o.channel""",
        (f"-{weeks * 7} days",),
    )
    conn.execute("DELETE FROM gift_models")
    conn.execute(
        """INSERT INTO gift_models (model_sku, gift_share, units, updated_at)
           SELECT model_sku, SUM(is_gift * quantity) / SUM(quantity), SUM(quantity), datetime('now', 'localtime')
           FROM v_valid_lines
           GROUP BY model_sku
           HAVING SUM(quantity) > 0 AND SUM(is_gift * quantity) >= ? * SUM(quantity)""",
        (GIFT_HEAVY_SHARE,),
    )


def get_state(conn, key, default=None):
    row = conn.execute("SELECT value FROM sync_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_state(conn, key, value):
    conn.execute(
        "INSERT INTO sync_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


if __name__ == "__main__":
    init_db()
    conn = get_conn()
    refresh_derived_tables(conn)
    conn.commit()
    for r in conn.execute("SELECT * FROM channel_fee_rates ORDER BY ecom_fee_rate DESC"):
        print(f"  {r['channel']:<12} phí sàn {r['ecom_fee_rate']:.1%} ({r['orders']} đơn thành công)")
    gifts = conn.execute(
        """SELECT g.model_sku, g.gift_share, g.units, COALESCE(p.name, '') AS name FROM gift_models g
           LEFT JOIN products p ON p.sku = g.model_sku AND (p.parent_id IS NULL OR p.parent_id <= 0)
           ORDER BY g.units DESC"""
    ).fetchall()
    print(f"  Mẫu quà tặng kèm ({len(gifts)}): " + " · ".join(f"{g['model_sku']} {g['gift_share']:.0%}" for g in gifts))
    conn.close()
    print(f"DB sẵn sàng tại {DB_PATH}")
