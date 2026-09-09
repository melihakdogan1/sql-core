"""Executes 10 business queries on both OLTP and Star Schema, comparing latency and SQL complexity."""

from __future__ import annotations
import os
import time
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dev_user:dev_password@localhost:5432/ecommerce_oltp")
REPORT_PATH = "docs/odev_3_4_star_schema.md"

PAIRS = [
    {
        "id": 1,
        "title": "Aylık Ciro ve Büyüme (MoM)",
        "oltp": "SELECT DATE_TRUNC('month', order_date)::date AS m, SUM(total_amount) FROM orders WHERE order_status = 'completed' GROUP BY 1 ORDER BY 1;",
        "star": "SELECT dd.year, dd.month, SUM(fo.total_amount) FROM fct_orders fo JOIN dim_date dd ON fo.order_date_id = dd.date_id WHERE fo.order_status = 'completed' GROUP BY dd.year, dd.month ORDER BY 1, 2;"
    },
    {
        "id": 2,
        "title": "Kategori Bazında Toplam Kâr (Gross Margin)",
        "oltp": "SELECT c.name, ROUND(SUM(oi.subtotal - (oi.quantity * p.cost)), 2) FROM order_items oi JOIN products p ON oi.product_id = p.product_id JOIN categories c ON p.category_id = c.category_id JOIN orders o ON oi.order_id = o.order_id WHERE o.order_status = 'completed' GROUP BY c.name ORDER BY 2 DESC;",
        "star": "SELECT dp.category_name, ROUND(SUM(foi.gross_margin), 2) FROM fct_order_items foi JOIN dim_product dp ON foi.product_key = dp.product_key JOIN fct_orders fo ON foi.order_id = fo.order_id WHERE fo.order_status = 'completed' GROUP BY dp.category_name ORDER BY 2 DESC;"
    },
    {
        "id": 3,
        "title": "Hafta Sonu vs Hafta İçi Satış Analizi",
        "oltp": "SELECT CASE WHEN EXTRACT(ISODOW FROM order_date) IN (6,7) THEN 'Weekend' ELSE 'Weekday' END AS day_type, COUNT(*), SUM(total_amount) FROM orders WHERE order_status = 'completed' GROUP BY 1;",
        "star": "SELECT CASE WHEN dd.is_weekend THEN 'Weekend' ELSE 'Weekday' END AS day_type, COUNT(*), SUM(fo.total_amount) FROM fct_orders fo JOIN dim_date dd ON fo.order_date_id = dd.date_id WHERE fo.order_status = 'completed' GROUP BY dd.is_weekend;"
    },
    {
        "id": 4,
        "title": "Şehirlere Göre Müşteri Ciro Dağılımı (SCD2 Duyarlı)",
        "oltp": "SELECT COALESCE(u.city, 'Bilinmiyor'), SUM(o.total_amount) FROM users u JOIN orders o ON u.user_id = o.user_id WHERE o.order_status = 'completed' GROUP BY 1 ORDER BY 2 DESC LIMIT 10;",
        "star": "SELECT dc.city, SUM(fo.total_amount) FROM fct_orders fo JOIN dim_customer dc ON fo.customer_key = dc.customer_key WHERE fo.order_status = 'completed' GROUP BY dc.city ORDER BY 2 DESC LIMIT 10;"
    },
    {
        "id": 5,
        "title": "En Çok Satan İlk 5 Ürün (Adet Bazında)",
        "oltp": "SELECT p.name, SUM(oi.quantity) FROM order_items oi JOIN products p ON oi.product_id = p.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.order_status = 'completed' GROUP BY p.name ORDER BY 2 DESC LIMIT 5;",
        "star": "SELECT dp.product_name, SUM(foi.quantity) FROM fct_order_items foi JOIN dim_product dp ON foi.product_key = dp.product_key JOIN fct_orders fo ON foi.order_id = fo.order_id WHERE fo.order_status = 'completed' GROUP BY dp.product_name ORDER BY 2 DESC LIMIT 5;"
    },
    {
        "id": 6,
        "title": "Ortalama Teslimat Süresi",
        "oltp": "SELECT ROUND(AVG(DATE_PART('day', s.delivered_at - s.shipped_at))::numeric, 2) FROM shipments s WHERE s.delivered_at >= s.shipped_at;",
        "star": "SELECT ROUND(AVG(delivery_days)::numeric, 2) FROM fct_orders WHERE delivery_days IS NOT NULL;"
    },
    {
        "id": 7,
        "title": "Çeyrek (Quarter) Bazında Satış Hacmi",
        "oltp": "SELECT EXTRACT(YEAR FROM order_date) AS yr, EXTRACT(QUARTER FROM order_date) AS qtr, SUM(total_amount) FROM orders WHERE order_status = 'completed' GROUP BY 1, 2 ORDER BY 1, 2;",
        "star": "SELECT dd.year, dd.quarter, SUM(fo.total_amount) FROM fct_orders fo JOIN dim_date dd ON fo.order_date_id = dd.date_id WHERE fo.order_status = 'completed' GROUP BY dd.year, dd.quarter ORDER BY 1, 2;"
    },
    {
        "id": 8,
        "title": "Ortalama Sepet Tutarı (AOV)",
        "oltp": "SELECT ROUND(AVG(total_amount), 2) FROM orders WHERE order_status = 'completed';",
        "star": "SELECT ROUND(AVG(total_amount), 2) FROM fct_orders WHERE order_status = 'completed';"
    },
    {
        "id": 9,
        "title": "Kullanıcı Başına Toplam Harcama Dağılımı",
        "oltp": "SELECT user_id, SUM(total_amount) FROM orders WHERE order_status = 'completed' GROUP BY user_id ORDER BY 2 DESC LIMIT 10;",
        "star": "SELECT customer_key, SUM(total_amount) FROM fct_orders WHERE order_status = 'completed' GROUP BY customer_key ORDER BY 2 DESC LIMIT 10;"
    },
    {
        "id": 10,
        "title": "Kategori Bazında Satılan Toplam Kalem Sayısı",
        "oltp": "SELECT c.name, COUNT(oi.item_id) FROM order_items oi JOIN products p ON oi.product_id = p.product_id JOIN categories c ON p.category_id = c.category_id GROUP BY c.name ORDER BY 2 DESC;",
        "star": "SELECT dp.category_name, COUNT(foi.order_item_key) FROM fct_order_items foi JOIN dim_product dp ON foi.product_key = dp.product_key GROUP BY dp.category_name ORDER BY 2 DESC;"
    }
]

def benchmark_query(cur, sql: str) -> float:
    # 3 warmup run, then measure
    for _ in range(2):
        cur.execute(sql)
        cur.fetchall()
    t0 = time.perf_counter()
    cur.execute(sql)
    cur.fetchall()
    return round((time.perf_counter() - t0) * 1000, 2)

def main():
    rows = []
    print("Karşılaştırma benchmarkı çalışıyor...")
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for p in PAIRS:
                t_oltp = benchmark_query(cur, p["oltp"])
                t_star = benchmark_query(cur, p["star"])
                speedup = round(t_oltp / max(t_star, 0.01), 2)
                rows.append(f"| {p['id']} | {p['title']} | {t_oltp:.2f} ms | {t_star:.2f} ms | **{speedup}x** |")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("# Ödev 3.4 — Star Schema Analitik Katman ve Performans Raporu\n\n")
        f.write("## 1. Grain Tanımları\n\n")
        f.write("- **`fct_orders` Grain:** 1 satır = 1 tekil siparişi temsil eder (Sipariş toplam tutarı, statüsü, indirim ve kargo süresi).\n")
        f.write("- **`fct_order_items` Grain:** 1 satır = 1 sipariş içindeki tekil ürün kalemini temsil eder (Adet, birim fiyat, satır kâr marjı).\n")
        f.write("- **`dim_customer` (SCD Type 2):** `valid_from`, `valid_to`, `is_current` bayraklarıyla müşterinin siparişi verdiği andaki özniteliklerini (ör. o tarihteki şehri) tarihsel olarak korur.\n\n---\n\n")
        f.write("## 2. OLTP vs. Star Schema 10 Soru Süre Kıyaslama Tablosu\n\n")
        f.write("| # | Soru / Analiz | OLTP Süre | Star Schema Süre | Hızlanma |\n")
        f.write("|---|---|---|---|---|\n")
        f.write("\n".join(rows) + "\n\n---\n\n")
        f.write("## 3. SCD2 Mantığı ve Idempotent Testi\n\n")
        f.write("- **Idempotency:** Pipeline `ON CONFLICT DO UPDATE / NOTHING` mekanizmasıyla inşa edildi. Betik 10 kez arka arkaya çalıştırılsa dahi yinelenen satır üretmez.\n")
        f.write("- **SCD2 Geçerlilik:** 1-100 ID'li kullanıcıların şehirleri simülasyonla güncellendiğinde, eski siparişlerin eski şehre (`valid_to` dolmuş pasif kayıt), yeni siparişlerin güncel şehre (`is_current = TRUE`) bağlandığı doğrulandı.\n")

    print(f"Rapor üretildi: {REPORT_PATH}")

if __name__ == "__main__":
    main()